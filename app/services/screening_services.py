from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['screening_service', 'enhanced_screening_service', 'database_screening_service', 'intelligent_screening_service', 'intelligent_screening_v2', 'screening_metric_display', 'factor_registry_service']:
    _sys.modules[f"app.services.{_sub}"] = _self_mod
    setattr(_self_mod, _sub.split(".")[0], _self_mod)

# === screening_metric_display.py ===

from collections.abc import Mapping
from typing import Any


METRIC_DISPLAY_VARIANTS = {
    "pe": {
        "default": ("pe", "PE"),
        "variants": (("pe_ttm", "PE(TTM)"), ("pe", "PE")),
    },
    "pb": {
        "default": ("pb", "PB"),
        "variants": (("pb_mrq", "PB(MRQ)"), ("pb", "PB")),
    },
}


def select_metric_display_spec(
    raw_conditions: list[dict[str, Any]] | None,
    order_by_field: str | None,
    metric_key: str,
) -> tuple[str, str]:
    config = METRIC_DISPLAY_VARIANTS[metric_key]
    variant_labels = {field: label for field, label in config["variants"]}

    for condition in raw_conditions or []:
        if not isinstance(condition, Mapping):
            continue
        field = condition.get("field")
        if field in variant_labels:
            return field, variant_labels[field]

    if order_by_field in variant_labels:
        return order_by_field, variant_labels[order_by_field]

    return config["default"]


def resolve_metric_value(item: Mapping[str, Any], selected_field: str, metric_key: str) -> Any:
    config = METRIC_DISPLAY_VARIANTS[metric_key]
    fields = [selected_field]
    fields.extend(field for field, _label in config["variants"] if field != selected_field)

    for field in fields:
        value = item.get(field)
        if value is not None:
            return value

    return None

# === factor_registry_service.py ===

from typing import Any, Dict, List, Optional

from app.models.screening import BASIC_FIELDS_INFO
from core.skill_runtime.factor_catalog import (
    FACTOR_RUNTIME_SEMANTIC_CONTRACTS,
    RECOMMENDED_FACTOR_PACKS,
    get_factor_definition,
    list_factor_definitions,
)
from core.skill_runtime.factor_schema import (
    P0_FACTOR_FIELD_SCHEMA,
    P0_PUBLIC_SCREENING_FIELDS,
    TECHNICAL_FACTOR_FIELD_SCHEMA,
    TECHNICAL_PUBLIC_SCREENING_FIELDS,
    get_factor_field_schema,
)


class FactorRegistryService:
    def __init__(self) -> None:
        self._p0_fields = set(P0_FACTOR_FIELD_SCHEMA.keys())
        self._technical_fields = set(TECHNICAL_FACTOR_FIELD_SCHEMA.keys())
        self._screening_fields = set(BASIC_FIELDS_INFO.keys())
        self._public_screening_fields = set(P0_PUBLIC_SCREENING_FIELDS) | set(TECHNICAL_PUBLIC_SCREENING_FIELDS)
        self._legacy_static_categories = {
            "basic": ["keyword", "symbol", "code", "name", "industry", "area", "market"],
            "market_value": ["total_mv", "circ_mv"],
            "financial": [],
            "trading": ["turnover_rate", "volume_ratio"],
            "price": ["close", "pct_chg", "amount"],
            "technical": [],
        }
        self._category_labels = {
            "basic": "基础条件",
            "market_value": "市值规模",
            "financial": "财务因子",
            "trading": "交易活跃度",
            "price": "价格表现",
            "technical": "技术因子",
        }
        self._category_order = ["basic", "market_value", "financial", "trading", "price", "technical"]
        self._hidden_field_names = {"code", "market"}

    def _infer_category_key(self, field_name: str, field_type: str) -> str:
        if field_type == "technical":
            return "technical"
        if field_name in {"keyword", "symbol", "code", "name", "industry", "area", "market", "is_st"}:
            return "basic"
        if field_name in {"total_mv", "circ_mv"}:
            return "market_value"
        if field_name in {"turnover_rate", "volume_ratio"}:
            return "trading"
        if field_name in {"close", "pct_chg", "amount"}:
            return "price"
        return "financial"

    @staticmethod
    def _dedupe_fields(fields: List[str]) -> List[str]:
        return list(dict.fromkeys(fields))

    @staticmethod
    def _serialize_basic_field_info(field_name: str) -> Optional[Dict[str, Any]]:
        field_info = BASIC_FIELDS_INFO.get(field_name)
        if field_info is None:
            return None

        return {
            "name": field_info.name,
            "display_name": field_info.display_name,
            "field_type": field_info.field_type.value,
            "data_type": field_info.data_type,
            "description": field_info.description,
            "unit": field_info.unit,
            "supported_operators": [operator.value for operator in field_info.supported_operators],
        }

    def _resolve_governance_scope(self, factor_id: str) -> str:
        if factor_id in self._p0_fields:
            return "p0"
        if factor_id in self._technical_fields:
            return "technical"
        return "catalog_only"

    def _build_screening_metadata(self, factor_id: str) -> Optional[Dict[str, Any]]:
        field_info = BASIC_FIELDS_INFO.get(factor_id)
        if field_info is None:
            return None

        return {
            "registered": True,
            "field_type": field_info.field_type.value,
            "data_type": field_info.data_type,
            "unit": field_info.unit or "",
            "supported_operators": [operator.value for operator in field_info.supported_operators],
            "is_public_screening_field": factor_id in self._public_screening_fields,
        }

    def _build_registry_item(self, factor_id: str) -> Optional[Dict[str, Any]]:
        schema = get_factor_field_schema(factor_id)
        catalog = get_factor_definition(factor_id)
        contract = FACTOR_RUNTIME_SEMANTIC_CONTRACTS.get(factor_id)

        if schema is None and catalog is None and contract is None:
            return None

        recommended_packs = [pack_id for pack_id, fields in RECOMMENDED_FACTOR_PACKS.items() if factor_id in fields]
        return {
            "factor_id": factor_id,
            "display_name": schema.display_name if schema else (catalog.display_name if catalog else factor_id),
            "governance_scope": self._resolve_governance_scope(factor_id),
            "schema": schema.to_dict() if schema else None,
            "catalog": catalog.to_dict() if catalog else None,
            "runtime_semantic_contract": contract.to_dict() if contract else None,
            "screening": self._build_screening_metadata(factor_id),
            "recommended_packs": recommended_packs,
            "is_registered_in_screening": factor_id in self._screening_fields,
            "is_public_screening_field": factor_id in self._public_screening_fields,
        }

    def list_registry(
        self,
        category: Optional[str] = None,
        governance_scope: str = "all",
        screening_only: bool = False,
    ) -> Dict[str, Any]:
        catalog_entries = list_factor_definitions(category=category)
        factor_ids = [entry["factor_id"] for entry in catalog_entries]

        if governance_scope == "p0":
            factor_ids = [factor_id for factor_id in factor_ids if factor_id in self._p0_fields]
        elif governance_scope == "technical":
            factor_ids = [factor_id for factor_id in factor_ids if factor_id in self._technical_fields]

        if screening_only:
            factor_ids = [factor_id for factor_id in factor_ids if factor_id in self._screening_fields]

        items = [self._build_registry_item(factor_id) for factor_id in factor_ids]
        items = [item for item in items if item is not None]

        return {
            "total": len(items),
            "filters": {
                "category": category,
                "governance_scope": governance_scope,
                "screening_only": screening_only,
            },
            "items": items,
        }

    def get_registry_item(self, factor_id: str) -> Optional[Dict[str, Any]]:
        return self._build_registry_item(factor_id)

    def list_screening_registry_items(self, public_only: bool = False) -> List[Dict[str, Any]]:
        items = self.list_registry(screening_only=True).get("items", [])
        if public_only:
            items = [item for item in items if item.get("is_public_screening_field")]
        return items

    def get_screening_field_info(self, field_name: str) -> Optional[Dict[str, Any]]:
        registry_item = self.get_registry_item(field_name)
        basic_field_info = self._serialize_basic_field_info(field_name)

        if registry_item is None and basic_field_info is None:
            return None

        screening = (registry_item or {}).get("screening") or {}
        schema = (registry_item or {}).get("schema") or {}
        catalog = (registry_item or {}).get("catalog") or {}

        if basic_field_info is None:
            basic_field_info = {
                "name": field_name,
                "display_name": registry_item.get("display_name") or field_name,
                "field_type": screening.get("field_type") or "catalog_only",
                "data_type": screening.get("data_type") or schema.get("data_type") or "string",
                "description": schema.get("description") or catalog.get("description") or "",
                "unit": screening.get("unit") or schema.get("unit") or None,
                "supported_operators": screening.get("supported_operators") or [],
            }

        return {
            **basic_field_info,
            "governance_scope": (registry_item or {}).get("governance_scope"),
            "is_registered_in_screening": bool((registry_item or {}).get("is_registered_in_screening", field_name in self._screening_fields)),
            "is_public_screening_field": bool((registry_item or {}).get("is_public_screening_field", False)),
            "recommended_packs": (registry_item or {}).get("recommended_packs", []),
            "ui_category": self._infer_category_key(field_name, str(basic_field_info.get("field_type") or "")),
            "ui_order": self._category_order.index(self._infer_category_key(field_name, str(basic_field_info.get("field_type") or ""))) if self._infer_category_key(field_name, str(basic_field_info.get("field_type") or "")) in self._category_order else len(self._category_order),
            "ui_visible": field_name not in self._hidden_field_names,
        }

    def list_supported_screening_fields(self) -> List[Dict[str, Any]]:
        fields: List[Dict[str, Any]] = []
        for field_name in BASIC_FIELDS_INFO.keys():
            field_info = self.get_screening_field_info(field_name)
            if field_info is not None:
                fields.append(field_info)
        return fields

    def get_legacy_screening_field_config(self) -> Dict[str, Any]:
        fields: Dict[str, Dict[str, Any]] = {}
        categories = {key: list(values) for key, values in self._legacy_static_categories.items()}
        visible_fields_by_category = {key: [] for key in self._category_order}

        for field_name in BASIC_FIELDS_INFO.keys():
            field_info = self._serialize_basic_field_info(field_name)
            if field_info is not None:
                fields[field_name] = field_info

        for item in self.list_screening_registry_items(public_only=True):
            factor_id = str(item.get("factor_id") or "").strip()
            if not factor_id:
                continue

            field_info = self.get_screening_field_info(factor_id)
            if field_info is None:
                continue
            fields[factor_id] = {key: value for key, value in field_info.items() if key in {
                "name", "display_name", "field_type", "data_type", "description", "unit", "supported_operators"
            }}

            field_type = ((item.get("screening") or {}).get("field_type") or "").strip()
            if field_type == "technical":
                categories["technical"].append(factor_id)
            elif factor_id in {"total_mv", "circ_mv"}:
                categories["market_value"].append(factor_id)
            elif factor_id not in categories["basic"] and factor_id not in categories["trading"] and factor_id not in categories["price"]:
                categories["financial"].append(factor_id)

        for field_name in fields.keys():
            full_info = self.get_screening_field_info(field_name)
            if not full_info or not full_info.get("ui_visible", True):
                continue
            category_key = str(full_info.get("ui_category") or self._infer_category_key(field_name, str(full_info.get("field_type") or "")))
            visible_fields_by_category.setdefault(category_key, []).append(field_name)

        return {
            "fields": fields,
            "categories": {key: self._dedupe_fields(values) for key, values in categories.items()},
            "ui_metadata": {
                "category_order": list(self._category_order),
                "category_labels": dict(self._category_labels),
                "hidden_fields": sorted(self._hidden_field_names),
                "visible_fields_by_category": {
                    key: self._dedupe_fields(values) for key, values in visible_fields_by_category.items()
                },
            },
        }

    def build_screening_fields_markdown(self, public_only: bool = False) -> str:
        items = self.list_screening_registry_items(public_only=public_only)
        if not items:
            return "- There are currently no filter fields available"

        sorted_items = sorted(
            items,
            key=lambda item: (
                item.get("screening", {}).get("field_type") or "",
                item.get("factor_id") or "",
            ),
        )

        lines: List[str] = []
        for item in sorted_items:
            screening = item.get("screening") or {}
            factor_id = str(item.get("factor_id") or "").strip()
            if not factor_id:
                continue

            display_name = str(item.get("display_name") or factor_id)
            description = str(
                (item.get("schema") or {}).get("description")
                or (item.get("catalog") or {}).get("description")
                or ""
            ).strip()
            data_type = str(screening.get("data_type") or (item.get("schema") or {}).get("data_type") or "")
            operators = screening.get("supported_operators") or []

            detail_parts: List[str] = [display_name]
            if description and description != display_name:
                detail_parts.append(description)
            if data_type:
                detail_parts.append(f"类型: {data_type}")
            if operators:
                detail_parts.append("操作符: " + "/".join(str(operator) for operator in operators))

            lines.append(f"- {factor_id}    " + "；".join(detail_parts))

        return "\n".join(lines)

    def build_screening_tool_description(self, max_fields: int = 20) -> str:
        items = self.list_screening_registry_items(public_only=True)
        field_names = [str(item.get("factor_id") or "").strip() for item in items]
        field_names = [field_name for field_name in field_names if field_name]

        preview = "/".join(field_names[:max_fields])
        remaining = max(len(field_names) - max_fields, 0)
        remaining_text = f" 等 {len(field_names)} 个字段" if remaining > 0 else " 等字段"

        return (
            "Bulk screen A-share stocks by multiple financial, trading and technical indicators."
            "The conditions are passed in as a JSON array, and each condition contains three fields: field, operator, and value."
            f"Supported filter fields are dynamically generated based on factor registry and currently include {preview}{remaining_text if preview else ''}. "
            "Supported operators:> < >= <= == != between in not_in contains. "
            "Returns a list of eligible stocks, including information such as code, name, industry, valuation, earnings quality, cash flow, solvency, dividend yield and technical indicators."
        )


_factor_registry_service: Optional[FactorRegistryService] = None


def get_factor_registry_service() -> FactorRegistryService:
    global _factor_registry_service
    if _factor_registry_service is None:
        _factor_registry_service = FactorRegistryService()
    return _factor_registry_service


def build_screening_fields_markdown(public_only: bool = False) -> str:
    return get_factor_registry_service().build_screening_fields_markdown(public_only=public_only)


def build_screening_tool_description(max_fields: int = 20) -> str:
    return get_factor_registry_service().build_screening_tool_description(max_fields=max_fields)


# === screening/eval_utils.py ===
"""
Utility functions for screening evaluation and DSL parsing.
Extracted from ScreeningService to separate concerns while keeping API unchanged.
"""

from typing import Any, Dict, List, Optional, Iterable
import pandas as pd
import numpy as np


def collect_fields_from_conditions(node: Dict[str, Any], allowed_fields: Iterable[str]) -> List[str]:
    if not node:
        return []
    if node.get("op") == "group" or "children" in node:
        fields: List[str] = []
        for c in node.get("children", []):
            fields.extend(collect_fields_from_conditions(c, allowed_fields))
        # de-duplicate keep order
        return list(dict.fromkeys(fields))
    f = node.get("field")
    rf = node.get("right_field")
    out: List[str] = []
    if isinstance(f, str) and f in allowed_fields:
        out.append(f)
    if isinstance(rf, str) and rf in allowed_fields:
        out.append(rf)
    return out


def evaluate_fund_conditions(snap: Dict[str, Any], node: Dict[str, Any], fund_fields: Iterable[str]) -> bool:
    if not node:
        return True
    # group
    if node.get("op") == "group" or "children" in node:
        logic = (node.get("logic") or "AND").upper()
        children = node.get("children", [])
        flags = [evaluate_fund_conditions(snap, c, fund_fields) for c in children]
        return all(flags) if logic == "AND" else any(flags)
    # leaf
    field = node.get("field")
    op = node.get("op")
    if field not in fund_fields:
        return True  # Non-fundamental fields are skipped in fundamental-only paths
    left = snap.get(field)
    if left is None:
        return False
    if node.get("right_field"):
        rf = node.get("right_field")
        right = snap.get(rf)
    else:
        right = node.get("value")
    try:
        if op == ">":
            return float(left) > float(right)
        if op == "<":
            return float(left) < float(right)
        if op == ">=":
            return float(left) >= float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == "==":
            return float(left) == float(right)
        if op == "!=":
            return float(left) != float(right)
        if op == "between":
            lo_hi = right if isinstance(right, (list, tuple)) else (None, None)
            lo, hi = lo_hi if isinstance(lo_hi, (list, tuple)) and len(lo_hi) == 2 else (None, None)
            if lo is None or hi is None:
                return False
            v = float(left)
            return float(lo) <= v <= float(hi)
    except Exception:
        return False
    return False


def evaluate_conditions(
    df: pd.DataFrame,
    node: Dict[str, Any],
    allowed_fields: Iterable[str],
    allowed_ops: Iterable[str],
) -> bool:
    if not node:
        return True
    # group node
    if node.get("op") == "group" or "children" in node:
        logic = (node.get("logic") or "AND").upper()
        children = node.get("children", [])
        if logic not in {"AND", "OR"}:
            logic = "AND"
        flags = [evaluate_conditions(df, c, allowed_fields, allowed_ops) for c in children]
        return all(flags) if logic == "AND" else any(flags)

    # Leaf: field comparison
    field = node.get("field")
    op = node.get("op")
    if field not in allowed_fields or op not in set(allowed_ops):
        return False

    # Requires last two rows (crossed)
    if op in {"cross_up", "cross_down"}:
        right_field = node.get("right_field")
        if right_field not in allowed_fields:
            return False
        if len(df) < 2:
            return False
        t0 = df.iloc[-1]
        t1 = df.iloc[-2]
        a0 = t0.get(field)
        a1 = t1.get(field)
        b0 = t0.get(right_field)
        b1 = t1.get(right_field)
        if any(pd.isna([a0, a1, b0, b1])):
            return False
        if op == "cross_up":
            return (a1 <= b1) and (a0 > b0)
        else:
            return (a1 >= b1) and (a0 < b0)

    # Normal comparison: most recent row
    t0 = df.iloc[-1]
    left = t0.get(field)
    if pd.isna(left):
        return False

    if node.get("right_field"):
        rf = node.get("right_field")
        if rf not in allowed_fields:
            return False
        right = t0.get(rf)
    else:
        right = node.get("value")

    try:
        if op == ">":
            return float(left) > float(right)
        if op == "<":
            return float(left) < float(right)
        if op == ">=":
            return float(left) >= float(right)
        if op == "<=":
            return float(left) <= float(right)
        if op == "==":
            return float(left) == float(right)
        if op == "!=":
            return float(left) != float(right)
        if op == "between":
            lo_hi = right if isinstance(right, (list, tuple)) else (None, None)
            lo, hi = lo_hi if isinstance(lo_hi, (list, tuple)) and len(lo_hi) == 2 else (None, None)
            if lo is None or hi is None:
                return False
            v = float(left)
            return float(lo) <= v <= float(hi)
    except Exception:
        return False
    return False


def safe_float(v: Any) -> Optional[float]:
    try:
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return None
        return float(v)
    except Exception:
        return None


_collect_fields_from_conditions_util = collect_fields_from_conditions
_evaluate_conditions_util = evaluate_conditions
_evaluate_fund_conditions_util = evaluate_fund_conditions
_safe_float_util = safe_float

# === enhanced_screening/utils.py ===
"""
Utility helpers for EnhancedScreeningService to separate analysis and conversion logic.
"""

from typing import Any, Dict, List, Optional

from app.models.screening import ScreeningCondition, FieldType, BASIC_FIELDS_INFO


def analyze_conditions(conditions: List[ScreeningCondition]) -> Dict[str, Any]:
    analysis = {
        "total_conditions": len(conditions),
        "database_supported_conditions": 0,
        "technical_conditions": 0,
        "fundamental_conditions": 0,
        "basic_conditions": 0,
        "can_use_database": True,
        "needs_technical_indicators": False,
        "unsupported_fields": [],
        "condition_types": [],
    }

    for condition in conditions:
        field = condition.field

        if field in BASIC_FIELDS_INFO:
            field_info = BASIC_FIELDS_INFO[field]
            field_type = field_info.field_type

            if field_type == FieldType.BASIC:
                analysis["basic_conditions"] += 1
            elif field_type == FieldType.FUNDAMENTAL:
                analysis["fundamental_conditions"] += 1
            elif field_type == FieldType.TECHNICAL:
                analysis["technical_conditions"] += 1

            analysis["condition_types"].append(field_type.value)

            if field in set(BASIC_FIELDS_INFO.keys()):
                analysis["database_supported_conditions"] += 1
            else:
                analysis["can_use_database"] = False
                analysis["unsupported_fields"].append(field)
        else:
            analysis["can_use_database"] = False
            analysis["needs_technical_indicators"] = True
            analysis["unsupported_fields"].append(field)

    if analysis["technical_conditions"] > 0 or analysis["needs_technical_indicators"]:
        analysis["needs_technical_indicators"] = True

    return analysis


def convert_conditions_to_traditional_format(conditions: List[ScreeningCondition]) -> Dict[str, Any]:
    traditional_conditions: Dict[str, Any] = {}

    for condition in conditions:
        field = condition.field
        operator = condition.operator
        value = condition.value

        if operator == "between" and isinstance(value, list) and len(value) == 2:
            traditional_conditions[field] = {"min": value[0], "max": value[1]}
        elif operator in [">", "<", ">=", "<="]:
            traditional_conditions[field] = {operator: value}
        elif operator == "==":
            traditional_conditions[field] = value
        elif operator in ["in", "not_in"]:
            traditional_conditions[field] = {operator: value}
        else:
            traditional_conditions[field] = {operator: value}

    return traditional_conditions



# === screening_service.py ===

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import pandas as pd
import numpy as np

# Unified indicator library
from tradingagents.tools.analysis.indicators import IndicatorSpec, compute_many
# Unified multi-data source DF interface (downgraded by priority)
from tradingagents.dataflows.data_source_manager import get_data_source_manager
from tradingagents.dataflows.providers.china.fundamentals_snapshot import get_cn_fund_snapshot


# screening.eval_utils inlined above

# --- DSL constraint ---
ALLOWED_FIELDS = {
    # Original quotes (unified into lowercase columns)
    "open", "high", "low", "close", "vol", "amount",
    # derived
    "pct_chg",  # The day's increase or decrease
    # Indicators (fixed parameters)
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "dif", "dea", "macd_hist",
    "rsi14",
    "boll_mid", "boll_upper", "boll_lower",
    "atr14",
    "kdj_k", "kdj_d", "kdj_j",
    # Reserved: Fundamentals (subsequent implementation)
    "pe", "pb", "roe", "market_cap",
}

# Category: basic market field, technical indicator field, fundamental field
BASE_FIELDS = {"open", "high", "low", "close", "vol", "amount", "pct_chg"}
TECH_FIELDS = {
    "ma5", "ma10", "ma20", "ma60",
    "ema12", "ema26",
    "dif", "dea", "macd_hist",
    "rsi14",
    "boll_mid", "boll_upper", "boll_lower",
    "atr14",
    "kdj_k", "kdj_d", "kdj_j",
}
FUND_FIELDS = {"pe", "pb", "roe", "market_cap"}

ALLOWED_OPS = {">", "<", ">=", "<=", "==", "!=", "between", "cross_up", "cross_down"}


@dataclass
class ScreeningParams:
    market: str = "CN"
    date: Optional[str] = None  # YYYY-MM-DD, None=Last trading day
    adj: str = "qfq"  # Reserved parameters. The current implementation uses Tdx data and does not distinguish between restoration rights.
    limit: int = 50
    offset: int = 0
    order_by: Optional[List[Dict[str, str]]] = None  # [{field, direction}]


import logging
logger = logging.getLogger("agents")

class ScreeningService:
    def __init__(self):
        # Data sources are obtained through the unified DF interface and are not directly bound to specific sources.
        self.provider = None

    # --- public entrance ---
    def run(self, conditions: Dict[str, Any], params: ScreeningParams) -> Dict[str, Any]:
        symbols = self._get_universe()
        # In order to control the duration, first limit the sample size (later use batch/caching optimization)
        symbols = symbols[:120]

        end_date = datetime.now()
        start_date = end_date - timedelta(days=220)
        end_s = end_date.strftime("%Y-%m-%d")
        start_s = start_date.strftime("%Y-%m-%d")

        results: List[Dict[str, Any]] = []

        # Analyze the fields involved in the conditions to determine whether technical indicators/markets are needed
        needed_fields = self._collect_fields_from_conditions(conditions)
        order_fields = {o.get("field") for o in (params.order_by or []) if o.get("field")}
        all_needed = set(needed_fields) | set(order_fields)
        need_tech = any(f in TECH_FIELDS for f in all_needed)
        need_base = any(f in BASE_FIELDS for f in all_needed) or need_tech
        need_fund = any(f in FUND_FIELDS for f in all_needed)

        for code in symbols:
            try:
                dfc = None
                last = None

                # If you need basic market conditions/technical indicators, take the K-line
                if need_base:
                    manager = get_data_source_manager()
                    df = manager.get_stock_dataframe(code, start_s, end_s)
                    if df is None or df.empty:
                        continue
                    # Uniformly listed in lowercase
                    dfu = df.rename(columns={
                        "Open": "open", "High": "high", "Low": "low", "Close": "close",
                        "Volume": "vol", "Amount": "amount"
                    }).copy()
                    # Calculate the derivation:pct_chg
                    if "close" in dfu.columns:
                        dfu["pct_chg"] = dfu["close"].pct_change() * 100.0

                    # Calculated only when technical indicators are required
                    if need_tech:
                        specs = [
                            IndicatorSpec("ma", {"n": 5}),
                            IndicatorSpec("ma", {"n": 10}),
                            IndicatorSpec("ma", {"n": 20}),
                            IndicatorSpec("ema", {"n": 12}),
                            IndicatorSpec("ema", {"n": 26}),
                            IndicatorSpec("macd"),
                            IndicatorSpec("rsi", {"n": 14}),
                            IndicatorSpec("boll", {"n": 20, "k": 2}),
                            IndicatorSpec("atr", {"n": 14}),
                            IndicatorSpec("kdj", {"n": 9, "m1": 3, "m2": 3}),
                        ]
                        dfc = compute_many(dfu, specs)
                    else:
                        dfc = dfu

                    last = dfc.iloc[-1]

                # Evaluation conditions (if the conditions are entirely fundamental and do not involve market/technical conditions, you can skip the K line here)
                passes = True
                if need_base:
                    passes = self._evaluate_conditions(dfc, conditions)
                elif need_fund and not need_base and not need_tech:
                    # Fundamental conditions only: Use fundamental snapshots to determine
                    snap = get_cn_fund_snapshot(code)
                    if not snap:
                        passes = False
                    else:
                        passes = self._evaluate_fund_conditions(snap, conditions)

                if passes:
                    item = {"code": code}
                    if last is not None:
                        item.update({
                            "close": self._safe_float(last.get("close")),
                            "pct_chg": self._safe_float(last.get("pct_chg")),
                            "amount": self._safe_float(last.get("amount")),
                            "ma20": self._safe_float(last.get("ma20")) if need_tech else None,
                            "rsi14": self._safe_float(last.get("rsi14")) if need_tech else None,
                            "kdj_k": self._safe_float(last.get("kdj_k")) if need_tech else None,
                            "kdj_d": self._safe_float(last.get("kdj_d")) if need_tech else None,
                            "kdj_j": self._safe_float(last.get("kdj_j")) if need_tech else None,
                            "dif": self._safe_float(last.get("dif")) if need_tech else None,
                            "dea": self._safe_float(last.get("dea")) if need_tech else None,
                            "macd_hist": self._safe_float(last.get("macd_hist")) if need_tech else None,
                        })
                    results.append(item)
            except Exception:
                continue

        total = len(results)
        # sort
        if params.order_by:
            for order in reversed(params.order_by):  # The latter has low priority
                f = order.get("field")
                d = order.get("direction", "desc").lower()
                if f in ALLOWED_FIELDS:
                    results.sort(key=lambda x: (x.get(f) is None, x.get(f)), reverse=(d == "desc"))

        # Pagination
        start = params.offset or 0
        end = start + (params.limit or 50)
        page_items = results[start:end]

        return {
            "total": total,
            "items": page_items,
        }
    def _evaluate_fund_conditions(self, snap: Dict[str, Any], node: Dict[str, Any]) -> bool:
        """Delegate fundamental condition evaluation to utils to keep service slim."""
        return _evaluate_fund_conditions_util(snap, node, FUND_FIELDS)


    def _collect_fields_from_conditions(self, node: Dict[str, Any]) -> List[str]:
        """Delegate field collection to utils."""
        return _collect_fields_from_conditions_util(node, ALLOWED_FIELDS)

    # --- Internal: DSL Assessment ---
    def _evaluate_conditions(self, df: pd.DataFrame, node: Dict[str, Any]) -> bool:
        """Delegate technical/base condition evaluation to utils."""
        return _evaluate_conditions_util(df, node, ALLOWED_FIELDS, ALLOWED_OPS)

    # --- Tools ---
    def _safe_float(self, v: Any) -> Optional[float]:
        """Delegate numeric coercion to utils."""
        return _safe_float_util(v)

    def _get_universe(self) -> List[str]:
        """Get the A-share code collection: Get all A-share stock codes from the MongoDB stock_basic_info collection"""
        try:
            from app.core.database import get_mongo_db

            db = get_mongo_db()
            collection = db.stock_basic_info

            # Query all A-share stock codes (compatible with different data structures)
            cursor = collection.find(
                {
                    "$or": [
                        {"market_info.market": "CN"},  # new data structure
                        {"category": "stock_cn"},      # old data structure
                        {"market": {"$in": ["主板", "创业板", "科创板", "北交所"]}}  # By market type
                    ]
                },
                {"code": 1, "_id": 0}
            )

            # Get all stock codes simultaneously
            codes = [doc.get("code") for doc in cursor if doc.get("code")]

            if codes:
                logger.info(f"📊 从 MongoDB 获取到 {len(codes)} 只A股股票")
                return codes
            else:
                # If the database is empty, return common stock codes as a guide
                logger.warning("⚠️ MongoDB No stock data found in, use the bottom stock list")
                return ["000001", "000002", "000858", "600519", "600036", "601318", "300750"]

        except Exception as e:
            logger.error(f"❌ Failed to get stock list from MongoDB: {e}")
            # Return common stock codes as a backup when exceptions occur
            return ["000001", "000002", "000858", "600519", "600036", "601318", "300750"]


# === enhanced_screening_service.py ===
"""
Enhanced stock screening service
Combining database optimization and traditional screening methods to provide efficient stock screening functions
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.models.screening import ScreeningCondition, FieldType, BASIC_FIELDS_INFO

logger = logging.getLogger(__name__)

_analyze_conditions_util = analyze_conditions
_convert_to_traditional_util = convert_conditions_to_traditional_format
from app.core.database import get_mongo_db


class EnhancedScreeningService:
    """增强的股票筛选服务"""

    def __init__(self):
        self.db_service = get_database_screening_service()
        self.traditional_service = ScreeningService()
        self.factor_registry_service = get_factor_registry_service()

        # Fields that support database optimization
        self.db_supported_fields = set(BASIC_FIELDS_INFO.keys())

    async def screen_stocks(
        self,
        conditions: List[ScreeningCondition],
        market: str = "CN",
        date: Optional[str] = None,
        adj: str = "qfq",
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[List[Dict[str, str]]] = None,
        use_database_optimization: bool = True
    ) -> Dict[str, Any]:
        """
        Smart Stock Screening

        Args:
            conditions: filter list
            market: market
            date: transaction date
            adj: Restoration method
            limit: Return quantity limit
            offset: offset
            order_by: Sorting conditions
            use_database_optimization: Whether to use database optimization

        Returns:
            Dict: Filter results
        """
        start_time = time.time()

        try:
            # Analyze filters
            analysis = self._analyze_conditions(conditions)
            database_can_handle = await self.db_service.can_handle_conditions(conditions)

            # Decide which filter to use
            if (use_database_optimization and
                analysis["can_use_database"] and
                database_can_handle):

                # Use database optimization filtering
                result = await self._screen_with_database(
                    conditions, limit, offset, order_by
                )
                optimization_used = "database"
                source = "mongodb"

            else:
                # Use traditional filtering
                result = await self._screen_with_traditional_method(
                    conditions, market, date, adj, limit, offset, order_by
                )
                optimization_used = "traditional"
                source = "api"

            # Extract items/total
            items = result[0] if isinstance(result, tuple) else result.get("items", [])
            total = result[1] if isinstance(result, tuple) else result.get("total", 0)

            # If the database optimization path is used, enrichment is performed from the database quotation table (to avoid external calls during requests)
            if source == "mongodb" and items:
                try:
                    db = get_mongo_db()
                    coll = db["market_quotes"]
                    codes = [str(it.get("code")).zfill(6) for it in items if it.get("code")]
                    if codes:
                        cursor = coll.find(
                            {"code": {"$in": codes}},
                            projection={"_id": 0, "code": 1, "close": 1, "pct_chg": 1, "amount": 1},
                        )
                        quotes_list = await cursor.to_list(length=len(codes))
                        quotes_map = {str(d.get("code")).zfill(6): d for d in quotes_list}
                        for it in items:
                            key = str(it.get("code")).zfill(6)
                            q = quotes_map.get(key)
                            if not q:
                                continue
                            if q.get("close") is not None:
                                it["close"] = q.get("close")
                            if q.get("pct_chg") is not None:
                                it["pct_chg"] = q.get("pct_chg")
                            if q.get("amount") is not None:
                                it["amount"] = q.get("amount")
                except Exception as enrich_err:
                    logger.warning(f"Real-time market information enrichment failed (ignored): {enrich_err}")

            # Add real-time to filter results PE/PB
            if items:
                try:
                    items = await self._enrich_results_with_realtime_metrics(items)
                except Exception as enrich_err:
                    logger.warning(f"Real-time PE/PB enrichment failed (ignored): {enrich_err}")

            # Calculation time
            took_ms = int((time.time() - start_time) * 1000)

            # Return results
            return {
                "total": total,
                "items": items,
                "took_ms": took_ms,
                "optimization_used": optimization_used,
                "source": source,
                "analysis": {
                    **analysis,
                    "database_can_handle": database_can_handle,
                }
            }

        except Exception as e:
            logger.error(f"❌ 股票筛选失败: {e}")
            took_ms = int((time.time() - start_time) * 1000)

            return {
                "total": 0,
                "items": [],
                "took_ms": took_ms,
                "optimization_used": "none",
                "source": "error",
                "error": str(e)
            }

    def _analyze_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """Delegate condition analysis to utils."""
        analysis = _analyze_conditions_util(conditions)
        logger.info(f"📊 筛选条件分析: {analysis}")
        return analysis

    async def _screen_with_database(
        self,
        conditions: List[ScreeningCondition],
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """使用数据库优化筛选"""
        logger.info("🚀 使用数据库优化筛选")

        return await self.db_service.screen_stocks(
            conditions=conditions,
            limit=limit,
            offset=offset,
            order_by=order_by
        )

    async def _screen_with_traditional_method(
        self,
        conditions: List[ScreeningCondition],
        market: str,
        date: Optional[str],
        adj: str,
        limit: int,
        offset: int,
        order_by: Optional[List[Dict[str, str]]]
    ) -> Dict[str, Any]:
        """使用传统筛选方法"""
        logger.info("🔄 使用传统筛选方法")

        # Convert conditional formats to formats supported by legacy services
        traditional_conditions = self._convert_conditions_to_traditional_format(conditions)

        # Create filter parameters
        params = ScreeningParams(
            market=market,
            date=date,
            adj=adj,
            limit=limit,
            offset=offset,
            order_by=order_by
        )

        # Perform traditional screening
        result = self.traditional_service.run(traditional_conditions, params)

        return result

    def _convert_conditions_to_traditional_format(
        self,
        conditions: List[ScreeningCondition]
    ) -> Dict[str, Any]:
        """Delegate condition conversion to utils."""
        return _convert_to_traditional_util(conditions)

    async def _enrich_results_with_realtime_metrics(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Add PE/PB for filtering results (use static data to avoid performance issues)

        Args:
            items: Filter the results list

        Returns:
            List[Dict]: List of results after enrichment
        """
        # 🔥 Stock screening scenario: directly use the static data in stock_basic_info PE/PB
        # Reason: Computing dynamic PE in batches can cause serious performance issues (multiple collections are queried for each stock)
        # Static PE is based on the closing price of the latest trading day, which is accurate enough for screening scenarios.

        logger.info(f"📊 [筛选结果富集] 使用静态PE/PB（避免性能问题），共 {len(items)} 只股票")

        # Note: PE/PB in items already comes from stock_basic_info, no additional processing is required here.
        # If real-time PE is needed in the future, it can be calculated separately on the individual stock details page.

        return items

    async def get_field_info(self, field: str) -> Optional[Dict[str, Any]]:
        """
        Get field information

        Args:
            field: Field name

        Returns:
            Dict: Field information
        """
        field_info = self.factor_registry_service.get_screening_field_info(field)
        if field_info is None:
            return None

        stats = await self.db_service.get_field_statistics(field)

        available_values = None
        if field_info.get("data_type") == "string":
            available_values = await self.db_service.get_available_values(field)

        return {
            **field_info,
            "statistics": stats,
            "available_values": available_values,
        }

    async def get_all_supported_fields(self) -> List[Dict[str, Any]]:
        """获取所有支持的字段信息"""
        fields = []

        for field_name in self.factor_registry_service.get_legacy_screening_field_config()["fields"].keys():
            field_info = await self.get_field_info(field_name)
            if field_info:
                fields.append(field_info)

        return fields

    async def validate_conditions(self, conditions: List[ScreeningCondition]) -> Dict[str, Any]:
        """
        Validate filters

        Args:
            conditions: filter list

        Returns:
            Dict: Verification results
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }

        for i, condition in enumerate(conditions):
            field = condition.field
            operator = condition.operator
            value = condition.value

            # Check if the field supports
            if field not in BASIC_FIELDS_INFO:
                validation_result["errors"].append(
                    f"条件 {i+1}: 不支持的字段 '{field}'"
                )
                validation_result["valid"] = False
                continue

            field_info = BASIC_FIELDS_INFO[field]

            # Check if the operator is supported
            if operator not in [op.value for op in field_info.supported_operators]:
                validation_result["errors"].append(
                    f"条件 {i+1}: 字段 '{field}' 不支持操作符 '{operator}'"
                )
                validation_result["valid"] = False

            # Check value type and range
            if field_info.data_type == "number":
                if operator == "between":
                    if not isinstance(value, list) or len(value) != 2:
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符需要两个数值"
                        )
                        validation_result["valid"] = False
                    elif not all(isinstance(v, (int, float)) for v in value):
                        validation_result["errors"].append(
                            f"条件 {i+1}: between操作符的值必须是数字"
                        )
                        validation_result["valid"] = False
                elif not isinstance(value, (int, float)):
                    validation_result["errors"].append(
                        f"条件 {i+1}: 数值字段 '{field}' 的值必须是数字"
                    )
                    validation_result["valid"] = False

        return validation_result


# Global service instance
_enhanced_screening_service: Optional[EnhancedScreeningService] = None


def get_enhanced_screening_service() -> EnhancedScreeningService:
    """获取增强筛选服务实例"""
    global _enhanced_screening_service
    if _enhanced_screening_service is None:
        _enhanced_screening_service = EnhancedScreeningService()
    return _enhanced_screening_service

# === database_screening_service.py ===
"""
Stock screening service based on MongoDB
Use basic stock information in local databases for efficient screening
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

from app.core.database import get_mongo_db
from core.skill_runtime.fundamental_factors import (
    _build_factor_diagnostics,
    _build_growth_factor_warnings,
    _build_quality_factor_warnings,
    _build_value_factor_warnings,
    _compute_cagr,
    _compute_yoy_growth,
    _estimate_altman_z_score,
    _estimate_beneish_m_score,
    _estimate_interest_coverage,
    _estimate_piotroski_f_score,
    _estimate_roic,
)
# from app.models.screening import ScreeningCondition  # Avoid circular imports

logger = logging.getLogger(__name__)


class DatabaseScreeningService:
    """基于数据库的股票筛选服务"""
    
    def __init__(self):
        # Use views instead of basic information tables. The views already contain real-time market data.
        self.collection_name = "stock_screening_view"
        
        # Supported basic information field mapping
        self.basic_fields = {
            # Basic information
            "code": "code",
            "name": "name", 
            "industry": "industry",
            "area": "area",
            "market": "market",
            "list_date": "list_date",
            
            # Market capitalization information (billion)
            "total_mv": "total_mv",      # Total market capitalization
            "circ_mv": "circ_mv",        # Circulation market value
            "market_cap": "total_mv",    # market capitalization alias

            # financial indicators
            "pe": "pe",                  # P/E ratio
            "pb": "pb",                  # price to book ratio
            "pe_ttm": "pe_ttm",         # rolling price to earnings ratio
            "ps_ttm": "ps_ttm",         # rolling price-to-sales ratio
            "pb_mrq": "pb_mrq",         # Latest price-to-book ratio
            "roe": "roe",                # Return on equity (latest period)
            "roa": "roa",                # return on total assets
            "gross_margin": "gross_margin",          # Gross profit margin
            "netprofit_margin": "netprofit_margin",  # net profit margin
            "revenue_ttm": "revenue_ttm",            # rolling revenue
            "net_profit_ttm": "net_profit_ttm",      # rolling net profit
            "n_cashflow_act": "n_cashflow_act",      # Net operating cash flow
            "revenue_yoy": "revenue_yoy",            # Year-on-year revenue (%)
            "net_profit_yoy": "net_profit_yoy",      # Net profit year-on-year (%)
            "oper_profit_yoy": "oper_profit_yoy",    # Operating profit year-on-year (%)
            "peg": "peg",                            # PEG
            "roic": "roic",                          # ROIC (%)
            "cash_conversion": "cash_conversion",    # Profit to cash conversion rate
            "accrual_ratio": "accrual_ratio",        # accruals ratio (%)
            "asset_turnover": "asset_turnover",      # asset turnover rate
            "gross_profit_to_assets": "gross_profit_to_assets",  # Gross profit/total assets (%)
            "interest_coverage": "interest_coverage",  # interest coverage ratio
            "inventory_turnover": "inventory_turnover",  # Inventory turnover
            "receivable_turnover": "receivable_turnover",  # Accounts receivable turnover ratio
            "net_cash_position": "net_cash_position",  # Net Cash Position Proxy (%)
            "fcf": "fcf",                            # free cash flow
            "fcf_yield": "fcf_yield",                # free cash flow yield (%)
            "fcf_margin": "fcf_margin",              # free cash flow rate (%)
            "ocf_yield": "ocf_yield",                # operating cash flow yield (%)
            "revenue_cagr_3y": "revenue_cagr_3y",    # Three-year revenue compound growth rate (%)
            "profit_cagr_3y": "profit_cagr_3y",      # Three-year profit compound growth rate (%)
            "working_capital_change": "working_capital_change",  # working capital changes (billion)

            # trading indicators
            "turnover_rate": "turnover_rate",  # turnover rate%
            "volume_ratio": "volume_ratio",    # Quantity ratio

            # Technical indicators (from technical snapshot materialized collection)
            "ma20": "ma20",
            "rsi14": "rsi14",
            "kdj_k": "kdj_k",
            "kdj_d": "kdj_d",
            "kdj_j": "kdj_j",
            "dif": "dif",
            "dea": "dea",
            "macd_hist": "macd_hist",

            # Extended financial metrics (calculated fields from stock_screening_view)
            "debt_to_assets": "debt_to_assets",      # Asset-liability ratio (%)
            "assets_to_eqt": "assets_to_eqt",        # equity multiplier
            "current_ratio": "current_ratio",        # current ratio
            "quick_ratio": "quick_ratio",            # quick ratio
            "cash_ratio": "cash_ratio",              # cash ratio
            "dividend_yield": "dividend_yield",      # dividend yield (%)
            "net_working_capital": "net_working_capital",  # net working capital (billion)
            "is_st": "is_st",                        # Whether ST shares (True/False)
            "report_period": "report_period",        # Latest financial reporting period

            # Search keywords (virtual fields)
            "keyword": "keyword",

            # Real-time market quotation field (requires related query from market_quotes)
            "pct_chg": "pct_chg",              # Increase or decrease%
            "amount": "amount",                # Transaction volume (10,000 yuan)
            "close": "close",                  # closing price
            "volume": "volume",                # Volume
        }
        
        # Supported operators
        self.operators = {
            ">": "$gt",
            "<": "$lt", 
            ">=": "$gte",
            "<=": "$lte",
            "==": "$eq",
            "!=": "$ne",
            "between": "$between",  # Custom processing
            "in": "$in",
            "not_in": "$nin",
            "contains": "$regex",   # string contains
        }
    
    async def can_handle_conditions(self, conditions: List[Dict[str, Any]]) -> bool:
        """
        Check if these conditions can be handled entirely by database filtering
        
        Args:
            conditions: filter list
            
        Returns:
            bool: can it be processed
        """
        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
            
            # Check if the field supports
            if field not in self.basic_fields:
                logger.debug(f"字段 {field} 不支持数据库筛选")
                return False
            
            # Check if the operator is supported
            if operator not in self.operators:
                logger.debug(f"操作符 {operator} 不支持数据库筛选")
                return False
        
        return True
    
    async def screen_stocks(
        self,
        conditions: List[Dict[str, Any]],
        limit: int = 50,
        offset: int = 0,
        order_by: Optional[List[Dict[str, str]]] = None,
        source: Optional[str] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Stock screening based on database (two stages: basic screening → Market filtering)

        Args:
            conditions: filter list
            limit: Return quantity limit
            offset: offset
            order_by: Sorting conditions [{"field": "total_mv", "direction": "desc"}]
            source: Data source (optional), the data source with the highest priority is used by default

        Returns:
            Tuple[List[Dict], int]: (Filter results, total quantity)
        """
        try:
            db = get_mongo_db()

            if not source:
                from app.core.data_source_priority import get_preferred_data_source_async
                source = await get_preferred_data_source_async(market_category="a_shares")
                logger.info(f"✅ [database_screening] final data source used: {source}")

            # Separate basic conditions and market conditions
            basic_conditions, quote_conditions = self._separate_conditions(conditions)

            # Build a basic query (only including non-quote fields)
            query = await self._build_query(basic_conditions)
            query["source"] = source

            # Build sorting criteria
            sort_conditions = self._build_sort_conditions(order_by)

            logger.info(f"📋 基础查询条件: {query}")
            logger.info(f"📋 行情筛选条件: {quote_conditions}")
            logger.info(f"📋 排序条件: {sort_conditions}")

            has_real_conditions = any(k != "source" for k in query)
            has_quote_conditions = len(quote_conditions) > 0

            # Fast path: no basic filtering + No market filtering → Check directly stock_basic_info
            if not has_real_conditions and not has_quote_conditions:
                logger.info("⚡ Use the fast path: direct query stock_basic_info")
                results, total_count = await self._query_basic_info_directly(
                    db, source, sort_conditions, limit, offset
                )
                codes = [r.get("code") for r in results if r.get("code")]
                if codes:
                    await self._enrich_with_quote_data(results, codes)
                return results, total_count

            # When there are market conditions, two stages of screening are required:
            # Stage 1 — Basic filter (stock_basic_info or view)
            if has_quote_conditions:
                # When filtering the market, first take the basic results (take more for secondary filtering)
                phase1_limit = min(max(limit * 20, 2000), 10000)
                logger.info(f"📋 第 1 阶段取 {phase1_limit} 条候选用于行情过滤")
            else:
                phase1_limit = limit

            # Decide whether to use a view or stock_basic_info
            # ⚠️ Performance fix: Disable use of stock_screening_view view
            # This view passes $lookup Relate market_quotes and stock_financial_periods,
            # Even count_documents triggers the entire aggregation pipeline, causing the query to timeout (>30s) . 
            # Subsequent _enrich_with_financial_data and _enrich_with_quote_data have
            # Use batch $in Query implements the same data enrichment function without going through views.
            if has_real_conditions:
                collection = db["stock_basic_info"]
                total_count = await collection.count_documents(query)
            else:
                collection = db["stock_basic_info"]
                total_count = min(phase1_limit + offset + 1000, 10000)

            cursor = collection.find(query)
            if sort_conditions:
                cursor = cursor.sort(sort_conditions)
            if not has_quote_conditions:
                cursor = cursor.skip(offset)
            cursor = cursor.limit(phase1_limit)

            results = []
            codes = []
            async for doc in cursor:
                result = self._format_result(doc)
                results.append(result)
                codes.append(doc.get("code"))

            # Supplement financial data in batches
            if codes:
                await self._enrich_with_financial_data(results, codes)

            # Supplement market data in batches (guarantee close/pct_chg can always be displayed)
            if codes:
                await self._enrich_with_quote_data(results, codes)

            # Stage 2 — Market conditions filter
            if has_quote_conditions:
                results = self._apply_quote_filter(results, quote_conditions)
                total_count = len(results)
                # The sorting field may be a quotation field and needs to be reordered in memory.
                if order_by:
                    sort_field = order_by[0].get("field", "total_mv")
                    sort_dir = order_by[0].get("direction", "desc")
                    reverse = sort_dir.lower() == "desc"
                    results.sort(
                        key=lambda x: x.get(sort_field) if isinstance(x.get(sort_field), (int, float)) else float("-inf"),
                        reverse=reverse,
                    )
                results = results[offset:offset + limit]

            logger.info(f"✅ 数据库筛选完成: 总数={total_count}, 返回={len(results)}, 数据源={source}")
            return results, total_count

        except Exception as e:
            logger.error(f"❌ 数据库筛选失败: {e}")
            raise Exception(f"数据库筛选失败: {str(e)}")
    
    async def _query_basic_info_directly(
        self,
        db,
        source: str,
        sort_conditions: List[Tuple[str, int]],
        limit: int,
        offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Query stock_basic_info directly to avoid the aggregation pipeline overhead of the view
        
        This is for simple queries (only source + sorting) optimization path
        """
        try:
            basic_info_collection = db["stock_basic_info"]
            
            # Build query conditions (source only)
            query = {"source": source}
            
            # Execute query (using index)
            cursor = basic_info_collection.find(query)
            
            # Apply sorting (using composite index)
            if sort_conditions:
                cursor = cursor.sort(sort_conditions)
            
            # Apply paging
            cursor = cursor.skip(offset).limit(limit)
            
            # Get results
            results = []
            codes = []
            async for doc in cursor:
                # Use a unified formatting method to ensure consistent formatting
                result = self._format_result(doc)
                results.append(result)
                codes.append(doc.get("code"))
            
            # Batch query financial data (ROE, etc.)
            if codes:
                await self._enrich_with_financial_data(results, codes)
            
            # Estimate totals (avoid count_documents)
            total_count = min(limit + offset + 1000, 10000)
            
            logger.info(f"✅ 快速路径查询完成: 返回={len(results)}, 数据源={source}")
            
            return results, total_count
            
        except Exception as e:
            logger.error(f"❌ 快速路径查询失败: {e}")
            raise
    
    async def _build_query(self, conditions: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build MongoDB query conditions"""
        query = {}

        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
            value = condition.get("value") if isinstance(condition, dict) else condition.value

            logger.info(f"🔍 [_build_query] Processing conditions: field={field}, operator={operator}, value={value}")

            # Special handling of keyword fields
            if field == "keyword":
                query["$or"] = [
                    {"code": {"$regex": str(value), "$options": "i"}},
                    {"name": {"$regex": str(value), "$options": "i"}},
                    {"symbol": {"$regex": str(value), "$options": "i"}}
                ]
                continue

            # Mapping field name
            db_field = self.basic_fields.get(field)
            if not db_field:
                continue
            
            # Handle special operators
            if operator == "between":
                # between The operation requires two values
                if isinstance(value, list) and len(value) == 2:
                    query[db_field] = {
                        "$gte": value[0],
                        "$lte": value[1]
                    }
            elif operator == "contains":
                # String contains (case insensitive)
                query[db_field] = {
                    "$regex": str(value),
                    "$options": "i"
                }
            elif operator in self.operators:
                # Standard operators
                mongo_op = self.operators[operator]
                query[db_field] = {mongo_op: value}
            
        return query
    
    def _build_sort_conditions(self, order_by: Optional[List[Dict[str, str]]]) -> List[Tuple[str, int]]:
        """构建排序条件"""
        if not order_by:
            # Sort by total market capitalization in descending order by default
            return [("total_mv", -1)]
        
        sort_conditions = []
        for order in order_by:
            field = order.get("field")
            direction = order.get("direction", "desc")
            
            # Mapping field name
            db_field = self.basic_fields.get(field)
            if not db_field:
                continue
            
            # Mapping sort direction
            sort_direction = -1 if direction.lower() == "desc" else 1
            sort_conditions.append((db_field, sort_direction))
        
        return sort_conditions
    
    async def _enrich_with_financial_data(self, results: List[Dict[str, Any]], codes: List[str]) -> None:
        """
        Query financial data in batches and populate the results

        Args:
            results: Filter the results list
            codes: Stock code list
        """
        try:
            db = get_mongo_db()
            financial_collection = db['stock_financial_periods']
            basic_info_collection = db['stock_basic_info']

            # 🔥 Use unified data source priority management functions
            from app.core.data_source_priority import get_preferred_data_source_async
            preferred_source = await get_preferred_data_source_async(market_category="a_shares")
            basic_info_map: Dict[str, Dict[str, Any]] = {}
            basic_info_cursor = basic_info_collection.find(
                {"code": {"$in": codes}, "source": preferred_source},
                {
                    "_id": 0,
                    "code": 1,
                    "source": 1,
                    "pe": 1,
                    "pe_ttm": 1,
                    "pb": 1,
                    "pb_mrq": 1,
                    "ps": 1,
                    "ps_ttm": 1,
                    "dividend_yield": 1,
                    "total_mv": 1,
                    "market_cap": 1,
                },
            )
            async for basic_info_doc in basic_info_cursor:
                basic_info_map[basic_info_doc.get("code")] = basic_info_doc

            def build_snapshot_record(snapshot: Dict[str, Any]) -> Dict[str, Any]:
                raw_balance = snapshot.get("raw_balance_sheet") or {}
                raw_income = snapshot.get("raw_income_statement") or {}
                raw_cashflow = snapshot.get("raw_cashflow_statement") or {}
                raw_indicators = snapshot.get("raw_financial_indicators") or {}
                return {
                    "report_period": snapshot.get("report_period"),
                    "revenue_ttm": snapshot.get("revenue_ttm"),
                    "revenue": snapshot.get("revenue"),
                    "oper_rev": snapshot.get("oper_rev"),
                    "net_profit_ttm": snapshot.get("net_profit_ttm"),
                    "net_profit": snapshot.get("net_profit"),
                    "net_income": snapshot.get("net_income"),
                    "total_profit": snapshot.get("total_profit"),
                    "oper_profit": snapshot.get("oper_profit"),
                    "operating_profit": snapshot.get("operating_profit"),
                    "ebit": snapshot.get("ebit"),
                    "oper_cost": snapshot.get("oper_cost"),
                    "oper_exp": snapshot.get("oper_exp"),
                    "admin_exp": snapshot.get("admin_exp"),
                    "rd_exp": snapshot.get("rd_exp"),
                    "fin_exp": snapshot.get("fin_exp"),
                    "roe": snapshot.get("roe"),
                    "roa": snapshot.get("roa"),
                    "gross_margin": snapshot.get("gross_margin"),
                    "netprofit_margin": snapshot.get("netprofit_margin"),
                    "debt_to_assets": snapshot.get("debt_to_assets"),
                    "assets_to_eqt": snapshot.get("assets_to_eqt"),
                    "current_ratio": snapshot.get("current_ratio"),
                    "quick_ratio": snapshot.get("quick_ratio"),
                    "cash_ratio": snapshot.get("cash_ratio"),
                    "total_assets": snapshot.get("total_assets"),
                    "total_cur_assets": snapshot.get("total_cur_assets"),
                    "total_nca": snapshot.get("total_nca"),
                    "total_cur_liab": snapshot.get("total_cur_liab"),
                    "total_liab": snapshot.get("total_liab"),
                    "total_equity": snapshot.get("total_equity"),
                    "total_ncl": snapshot.get("total_ncl"),
                    "money_cap": snapshot.get("money_cap"),
                    "fix_assets": snapshot.get("fix_assets"),
                    "accounts_receiv": snapshot.get("accounts_receiv"),
                    "inventories": snapshot.get("inventories"),
                    "n_cashflow_act": snapshot.get("n_cashflow_act"),
                    "n_cashflow_inv_act": snapshot.get("n_cashflow_inv_act"),
                    "n_cashflow_fin_act": snapshot.get("n_cashflow_fin_act"),
                    "balance_sheet": raw_balance,
                    "income_statement": raw_income,
                    "cashflow_statement": raw_cashflow,
                    "financial_indicators": raw_indicators,
                    "raw_data": {
                        "balance_sheet": [raw_balance] if raw_balance else [],
                        "income_statement": [raw_income] if raw_income else [],
                        "cashflow_statement": [raw_cashflow] if raw_cashflow else [],
                        "financial_indicators": [raw_indicators] if raw_indicators else [],
                    },
                }

            def is_newer_report_period(candidate: Any, current: Any) -> bool:
                candidate_value = str(candidate or "")
                current_value = str(current or "")
                return bool(candidate_value) and candidate_value > current_value

            snapshot_fields = (
                "roe",
                "roa",
                "gross_margin",
                "netprofit_margin",
                "revenue_ttm",
                "net_profit_ttm",
                "n_cashflow_act",
                "debt_to_assets",
                "assets_to_eqt",
                "current_ratio",
                "quick_ratio",
                "cash_ratio",
                "dividend_yield",
                "net_working_capital",
            )

            # Query the latest financial data in batches
            # Group by code and get the latest data for each code (only query the data source with the highest priority)
            pipeline = [
                {"$match": {"code": {"$in": codes}, "source": preferred_source}},
                {"$sort": {"code": 1, "report_period": -1, "ann_date": -1}},
                {"$group": {
                    "_id": "$code",
                    "roe": {"$first": "$roe"},
                    "roa": {"$first": "$roa"},
                    "net_profit": {"$first": "$net_profit"},
                    "total_profit": {"$first": "$total_profit"},
                    "oper_profit": {"$first": "$oper_profit"},
                    "netprofit_margin": {"$first": "$netprofit_margin"},
                    "gross_margin": {"$first": "$gross_margin"},
                    "netprofit_margin": {"$first": "$netprofit_margin"},
                    "revenue": {"$first": "$revenue"},
                    "oper_rev": {"$first": "$oper_rev"},
                    "net_income": {"$first": "$net_income"},
                    "total_assets": {"$first": "$total_assets"},
                    "total_nca": {"$first": "$total_nca"},
                    "fix_assets": {"$first": "$fix_assets"},
                    "oper_cost": {"$first": "$oper_cost"},
                    "oper_exp": {"$first": "$oper_exp"},
                    "admin_exp": {"$first": "$admin_exp"},
                    "rd_exp": {"$first": "$rd_exp"},
                    "fin_exp": {"$first": "$fin_exp"},
                    "ebit": {"$first": "$ebit"},
                    "operating_profit": {"$first": "$operating_profit"},
                    "pe_ttm": {"$first": "$pe_ttm"},
                    "revenue_ttm": {"$first": "$revenue_ttm"},
                    "net_profit_ttm": {"$first": "$net_profit_ttm"},
                    "n_cashflow_act": {"$first": "$n_cashflow_act"},
                    "n_cashflow_inv_act": {"$first": "$n_cashflow_inv_act"},
                    "n_cashflow_fin_act": {"$first": "$n_cashflow_fin_act"},
                    "revenue_yoy": {"$first": "$revenue_yoy"},
                    "net_profit_yoy": {"$first": "$net_profit_yoy"},
                    "oper_profit_yoy": {"$first": "$oper_profit_yoy"},
                    "roe": {"$first": "$roe"},
                    "roa": {"$first": "$roa"},
                    "assets_to_eqt": {"$first": "$assets_to_eqt"},
                    "debt_to_assets": {"$first": "$debt_to_assets"},
                    "current_ratio": {"$first": "$current_ratio"},
                    "quick_ratio": {"$first": "$quick_ratio"},
                    "cash_ratio": {"$first": "$cash_ratio"},
                    "dividend_yield": {"$first": "$dividend_yield"},
                    "total_cur_assets": {"$first": "$total_cur_assets"},
                    "total_cur_liab": {"$first": "$total_cur_liab"},
                    "total_liab": {"$first": "$total_liab"},
                    "total_equity": {"$first": "$total_equity"},
                    "money_cap": {"$first": "$money_cap"},
                    "total_ncl": {"$first": "$total_ncl"},
                    "accounts_receiv": {"$first": "$accounts_receiv"},
                    "inventories": {"$first": "$inventories"},
                    "period_snapshots": {
                        "$push": {
                            "total_cur_assets": "$total_cur_assets",
                            "total_cur_liab": "$total_cur_liab",
                            "total_assets": "$total_assets",
                            "total_liab": "$total_liab",
                            "total_ncl": "$total_ncl",
                            "fix_assets": "$fix_assets",
                            "accounts_receiv": "$accounts_receiv",
                            "inventories": "$inventories",
                            "revenue_ttm": "$revenue_ttm",
                            "revenue": "$revenue",
                            "oper_rev": "$oper_rev",
                            "net_profit_ttm": "$net_profit_ttm",
                            "net_profit": "$net_profit",
                            "net_income": "$net_income",
                            "total_profit": "$total_profit",
                            "oper_profit": "$oper_profit",
                            "operating_profit": "$operating_profit",
                            "ebit": "$ebit",
                            "oper_cost": "$oper_cost",
                            "oper_exp": "$oper_exp",
                            "admin_exp": "$admin_exp",
                            "rd_exp": "$rd_exp",
                            "fin_exp": "$fin_exp",
                            "roe": "$roe",
                            "roa": "$roa",
                            "gross_margin": "$gross_margin",
                            "netprofit_margin": "$netprofit_margin",
                            "debt_to_assets": "$debt_to_assets",
                            "assets_to_eqt": "$assets_to_eqt",
                            "current_ratio": "$current_ratio",
                            "quick_ratio": "$quick_ratio",
                            "cash_ratio": "$cash_ratio",
                            "n_cashflow_act": "$n_cashflow_act",
                            "n_cashflow_inv_act": "$n_cashflow_inv_act",
                            "n_cashflow_fin_act": "$n_cashflow_fin_act",
                            "total_nca": "$total_nca",
                            "total_equity": "$total_equity",
                            "money_cap": "$money_cap",
                            "raw_balance_sheet": "$raw_data.balance_sheet",
                            "raw_income_statement": "$raw_data.income_statement",
                            "raw_cashflow_statement": "$raw_data.cashflow_statement",
                            "raw_financial_indicators": "$raw_data.financial_indicators",
                            "report_period": "$report_period"
                        }
                    },
                    "report_period": {"$first": "$report_period"},
                }}
            ]

            financial_data_map = {}
            async for doc in financial_collection.aggregate(pipeline):
                code = doc.get("_id")
                debt_to_assets = doc.get("debt_to_assets")
                assets_to_eqt = doc.get("assets_to_eqt")
                current_ratio = doc.get("current_ratio")
                quick_ratio = doc.get("quick_ratio")
                cash_ratio = doc.get("cash_ratio")
                dividend_yield = doc.get("dividend_yield")
                total_cur_assets = doc.get("total_cur_assets")
                total_cur_liab = doc.get("total_cur_liab")
                total_liab = doc.get("total_liab")
                total_equity = doc.get("total_equity")
                money_cap = doc.get("money_cap")
                total_ncl = doc.get("total_ncl")
                accounts_receiv = doc.get("accounts_receiv")
                inventories = doc.get("inventories")
                net_working_capital = None
                if total_cur_assets is not None and total_cur_liab is not None:
                    net_working_capital = (total_cur_assets - total_cur_liab) / 1e8
                working_capital_change = None
                period_snapshots = doc.get("period_snapshots") or []
                if len(period_snapshots) > 1:
                    current_snapshot = period_snapshots[0] or {}
                    previous_snapshot = period_snapshots[1] or {}
                    current_nwc = None
                    previous_nwc = None
                    if current_snapshot.get("total_cur_assets") is not None and current_snapshot.get("total_cur_liab") is not None:
                        current_nwc = current_snapshot.get("total_cur_assets") - current_snapshot.get("total_cur_liab")
                    if previous_snapshot.get("total_cur_assets") is not None and previous_snapshot.get("total_cur_liab") is not None:
                        previous_nwc = previous_snapshot.get("total_cur_assets") - previous_snapshot.get("total_cur_liab")
                    if current_nwc is not None and previous_nwc is not None:
                        working_capital_change = (current_nwc - previous_nwc) / 1e8
                fcf = None
                if doc.get("n_cashflow_act") is not None and doc.get("n_cashflow_inv_act") is not None:
                    fcf = doc.get("n_cashflow_act") + doc.get("n_cashflow_inv_act")
                cash_conversion = None
                if doc.get("n_cashflow_act") is not None and doc.get("net_profit") not in (None, 0):
                    cash_conversion = doc.get("n_cashflow_act") / doc.get("net_profit")
                accrual_ratio = None
                if doc.get("net_profit") is not None and doc.get("n_cashflow_act") is not None and doc.get("total_assets") not in (None, 0):
                    accrual_ratio = (doc.get("net_profit") - doc.get("n_cashflow_act")) / doc.get("total_assets") * 100
                revenue_base = doc.get("revenue_ttm") if doc.get("revenue_ttm") not in (None, 0) else doc.get("revenue")
                fcf_margin = None
                if fcf is not None and revenue_base not in (None, 0):
                    fcf_margin = fcf / revenue_base * 100
                asset_turnover = None
                if revenue_base not in (None, 0) and doc.get("total_assets") not in (None, 0):
                    asset_turnover = revenue_base / doc.get("total_assets")
                gross_profit_to_assets = None
                if revenue_base not in (None, 0) and doc.get("gross_margin") is not None and doc.get("total_assets") not in (None, 0):
                    gross_profit_to_assets = revenue_base * doc.get("gross_margin") / 100 / doc.get("total_assets") * 100
                interest_coverage = None
                inventory_turnover = None
                cost_base = doc.get("oper_cost")
                if cost_base in (None, 0) and revenue_base not in (None, 0) and doc.get("gross_margin") is not None:
                    cost_base = revenue_base * (1 - doc.get("gross_margin") / 100)
                if cost_base not in (None, 0) and inventories not in (None, 0):
                    inventory_turnover = cost_base / inventories
                receivable_turnover = None
                if revenue_base not in (None, 0) and accounts_receiv not in (None, 0):
                    receivable_turnover = revenue_base / accounts_receiv
                net_cash_position = None
                if money_cap is not None and doc.get("total_assets") not in (None, 0):
                    debt_proxy = total_ncl
                    if debt_proxy is None and total_liab is not None and total_cur_liab is not None:
                        debt_proxy = total_liab - total_cur_liab
                    if debt_proxy is not None:
                        net_cash_position = (money_cap - max(debt_proxy, 0)) / doc.get("total_assets") * 100
                financial_records = [build_snapshot_record(snapshot) for snapshot in period_snapshots if snapshot]
                revenue_yoy = None
                net_profit_yoy = None
                oper_profit_yoy = None
                revenue_cagr_3y = None
                profit_cagr_3y = None
                roic = None
                piotroski_f_score = None
                beneish_m_score = None
                if financial_records:
                    latest_financial = financial_records[0]
                    factor_context = {
                        "symbol": code,
                        "basic_info": {},
                        "market_quotes": {},
                        "financial_records": financial_records,
                        "latest_financial": latest_financial,
                        "current_price": None,
                    }
                    revenue_yoy = _compute_yoy_growth(financial_records, "revenue")
                    net_profit_yoy = _compute_yoy_growth(financial_records, "net_profit")
                    oper_profit_yoy = _compute_yoy_growth(financial_records, "oper_profit")
                    revenue_cagr_3y = _compute_cagr(financial_records, (("revenue_ttm",), ("revenue",), ("oper_rev",)), 3)
                    profit_cagr_3y = _compute_cagr(financial_records, (("net_profit_ttm",), ("net_profit",), ("net_income",)), 3)
                    roic = _estimate_roic(latest_financial)
                    interest_coverage = _estimate_interest_coverage(latest_financial)
                    piotroski_f_score = _estimate_piotroski_f_score(factor_context)
                    beneish_m_score = _estimate_beneish_m_score(factor_context)
                financial_data_map[code] = {
                    "roe": doc.get("roe"),
                    "roa": doc.get("roa"),
                    "netprofit_margin": doc.get("netprofit_margin"),
                    "gross_margin": doc.get("gross_margin"),
                    "revenue_ttm": doc.get("revenue_ttm"),
                    "revenue_yoy": revenue_yoy,
                    "net_profit_ttm": doc.get("net_profit_ttm"),
                    "net_profit_yoy": net_profit_yoy,
                    "oper_profit_yoy": oper_profit_yoy,
                    "n_cashflow_act": doc.get("n_cashflow_act"),
                    "fcf": fcf,
                    "fcf_margin": fcf_margin,
                    "cash_conversion": cash_conversion,
                    "accrual_ratio": accrual_ratio,
                    "asset_turnover": asset_turnover,
                    "gross_profit_to_assets": gross_profit_to_assets,
                    "interest_coverage": interest_coverage,
                    "inventory_turnover": inventory_turnover,
                    "receivable_turnover": receivable_turnover,
                    "net_cash_position": net_cash_position,
                    "piotroski_f_score": piotroski_f_score,
                    "beneish_m_score": beneish_m_score,
                    "debt_to_assets": debt_to_assets,
                    "assets_to_eqt": assets_to_eqt,
                    "current_ratio": current_ratio,
                    "quick_ratio": quick_ratio,
                    "cash_ratio": cash_ratio,
                    "dividend_yield": dividend_yield,
                    "total_equity": total_equity,
                    "roic": roic,
                    "revenue_cagr_3y": revenue_cagr_3y,
                    "profit_cagr_3y": profit_cagr_3y,
                    "working_capital_change": working_capital_change,
                    "net_working_capital": net_working_capital,
                    "report_period": doc.get("report_period"),
                    "_financial_records": financial_records,
                }

            # Populate financial data into results
            for result in results:
                code = result.get("code")
                if code in financial_data_map:
                    financial_data = financial_data_map[code]
                    raw_basic_info = dict(basic_info_map.get(code) or {})
                    basic_info_context = {
                        **raw_basic_info,
                        "total_mv": raw_basic_info.get("total_mv", result.get("total_mv")),
                        "market_cap": raw_basic_info.get("market_cap", result.get("total_mv")),
                    }
                    latest_report_period = financial_data.get("report_period")
                    newer_snapshot = is_newer_report_period(latest_report_period, result.get("report_period"))
                    if latest_report_period is not None and (newer_snapshot or result.get("report_period") is None):
                        result["report_period"] = latest_report_period

                    for field_name in snapshot_fields:
                        field_value = financial_data.get(field_name)
                        if field_value is None:
                            continue
                        if newer_snapshot or result.get(field_name) is None:
                            result[field_name] = field_value

                    if newer_snapshot or result.get("pb_mrq") is None:
                        total_mv = result.get("total_mv")
                        total_equity = financial_data.get("total_equity")
                        if total_mv not in (None, 0) and total_equity not in (None, 0):
                            result["pb_mrq"] = (total_mv * 100000000) / total_equity
                    if newer_snapshot or result.get("pe_ttm") is None:
                        total_mv = result.get("total_mv")
                        net_profit_ttm = financial_data.get("net_profit_ttm")
                        if total_mv not in (None, 0) and net_profit_ttm not in (None, 0):
                            result["pe_ttm"] = (total_mv * 100000000) / net_profit_ttm
                    if result.get("asset_turnover") is None:
                        result["asset_turnover"] = financial_data.get("asset_turnover")
                    if result.get("gross_profit_to_assets") is None:
                        result["gross_profit_to_assets"] = financial_data.get("gross_profit_to_assets")
                    if result.get("interest_coverage") is None:
                        result["interest_coverage"] = financial_data.get("interest_coverage")
                    if result.get("inventory_turnover") is None:
                        result["inventory_turnover"] = financial_data.get("inventory_turnover")
                    if result.get("receivable_turnover") is None:
                        result["receivable_turnover"] = financial_data.get("receivable_turnover")
                    if result.get("net_cash_position") is None:
                        result["net_cash_position"] = financial_data.get("net_cash_position")
                    if result.get("piotroski_f_score") is None:
                        result["piotroski_f_score"] = financial_data.get("piotroski_f_score")
                    if result.get("beneish_m_score") is None:
                        result["beneish_m_score"] = financial_data.get("beneish_m_score")
                    if financial_data.get("revenue_yoy") is not None:
                        result["revenue_yoy"] = financial_data.get("revenue_yoy")
                    if financial_data.get("net_profit_yoy") is not None:
                        result["net_profit_yoy"] = financial_data.get("net_profit_yoy")
                    if financial_data.get("oper_profit_yoy") is not None:
                        result["oper_profit_yoy"] = financial_data.get("oper_profit_yoy")
                    if financial_data.get("revenue_cagr_3y") is not None:
                        result["revenue_cagr_3y"] = financial_data.get("revenue_cagr_3y")
                    if financial_data.get("profit_cagr_3y") is not None:
                        result["profit_cagr_3y"] = financial_data.get("profit_cagr_3y")
                    if result.get("fcf") is None:
                        result["fcf"] = financial_data.get("fcf")
                    if result.get("fcf_margin") is None:
                        result["fcf_margin"] = financial_data.get("fcf_margin")
                    if result.get("cash_conversion") is None:
                        result["cash_conversion"] = financial_data.get("cash_conversion")
                    if result.get("accrual_ratio") is None:
                        result["accrual_ratio"] = financial_data.get("accrual_ratio")
                    if financial_data.get("roic") is not None:
                        result["roic"] = financial_data.get("roic")
                    if result.get("peg") is None:
                        pe_ttm = result.get("pe_ttm")
                        growth = financial_data.get("net_profit_yoy")
                        if pe_ttm not in (None, 0) and growth not in (None, 0) and growth > 0:
                            result["peg"] = pe_ttm / growth
                    if result.get("fcf_yield") is None:
                        fcf = financial_data.get("fcf")
                        total_mv = result.get("total_mv")
                        if fcf is not None and total_mv not in (None, 0):
                            result["fcf_yield"] = fcf / (total_mv * 1e8) * 100
                    if result.get("ocf_yield") is None:
                        ocf = financial_data.get("n_cashflow_act")
                        total_mv = result.get("total_mv")
                        if ocf is not None and total_mv not in (None, 0):
                            result["ocf_yield"] = ocf / (total_mv * 1e8) * 100
                    if financial_data.get("working_capital_change") is not None:
                        result["working_capital_change"] = financial_data.get("working_capital_change")
                    if result.get("altman_z_score") is None:
                        total_mv = result.get("total_mv")
                        financial_records = financial_data.get("_financial_records") or []
                        if total_mv not in (None, 0) and financial_records:
                            altman_context = {
                                "symbol": code,
                                "basic_info": {"total_mv": total_mv},
                                "market_quotes": {},
                                "financial_records": financial_records,
                                "latest_financial": financial_records[0],
                                "current_price": None,
                            }
                            result["altman_z_score"] = _estimate_altman_z_score(altman_context)

                    financial_records = financial_data.get("_financial_records") or []
                    if financial_records:
                        latest_financial = financial_records[0]
                        diagnostics_context = {
                            "symbol": code,
                            "basic_info": basic_info_context,
                            "market_quotes": {},
                            "financial_records": financial_records,
                            "latest_financial": latest_financial,
                            "current_price": None,
                        }
                        cautious_factor_values = {
                            "piotroski_f_score": result.get("piotroski_f_score"),
                            "altman_z_score": result.get("altman_z_score"),
                            "beneish_m_score": result.get("beneish_m_score"),
                        }
                        factor_diagnostics = _build_factor_diagnostics(diagnostics_context, cautious_factor_values)
                        null_factor_diagnostics = {
                            field_name: diagnostic
                            for field_name, diagnostic in factor_diagnostics.items()
                            if result.get(field_name) is None
                        }
                        if null_factor_diagnostics:
                            result["factor_diagnostics"] = null_factor_diagnostics

                        factor_values_for_warnings = {
                            "pe_ttm": result.get("pe_ttm"),
                            "pb": result.get("pb"),
                            "pb_mrq": result.get("pb_mrq"),
                            "ps_ttm": result.get("ps_ttm"),
                            "dividend_yield": result.get("dividend_yield"),
                            "industry_pe_median": result.get("industry_pe_median"),
                            "industry_pb_median": result.get("industry_pb_median"),
                            "roic": result.get("roic"),
                            "interest_coverage": result.get("interest_coverage"),
                            "inventory_turnover": result.get("inventory_turnover"),
                            "net_cash_position": result.get("net_cash_position"),
                            "net_profit_ttm": result.get("net_profit_ttm"),
                            "fcf": result.get("fcf"),
                        }
                        factor_warnings = {
                            **_build_value_factor_warnings(diagnostics_context, factor_values_for_warnings, {}, {}),
                            **_build_quality_factor_warnings(diagnostics_context, factor_values_for_warnings),
                            **_build_growth_factor_warnings(diagnostics_context, factor_values_for_warnings),
                        }
                        if factor_warnings:
                            result["factor_warnings"] = factor_warnings

            logger.debug(f"✅ 已填充 {len(financial_data_map)} 条财务数据")

        except Exception as e:
            logger.warning(f"⚠️ 填充财务数据失败: {e}")
            # No exception is thrown, allowing the basic data to continue to be returned

    def _format_result(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """Format query results and use backend field names uniformly"""
        # Infer market type based on stock symbol
        code = doc.get("code", "")
        market_type = "A股"  # Default A shares
        if code:
            if code.startswith("6"):
                market_type = "A股"  # Shanghai
            elif code.startswith(("0", "3")):
                market_type = "A股"  # Shenzhen
            elif code.startswith("8") or code.startswith("4"):
                market_type = "A股"  # Beijing Exchange

        result = {
            # Basic information
            "code": doc.get("code"),
            "name": doc.get("name"),
            "industry": doc.get("industry"),
            "area": doc.get("area"),
            "market": market_type,  # Market type (A shares, US stocks, Hong Kong stocks)
            "board": doc.get("market"),  # Sectors (Main Board, GEM, Science and Technology Innovation Board, etc.)
            "exchange": doc.get("sse"),  # Exchanges (Shanghai Stock Exchange, Shenzhen Stock Exchange, etc.)
            "list_date": doc.get("list_date"),

            # Market value information (100 million yuan)
            "total_mv": doc.get("total_mv"),
            "circ_mv": doc.get("circ_mv"),

            # financial indicators
            "pe": doc.get("pe"),
            "pb": doc.get("pb"),
            "pe_ttm": doc.get("pe_ttm"),
            "ps_ttm": doc.get("ps_ttm"),
            "pb_mrq": doc.get("pb_mrq"),
            "roe": doc.get("roe"),
            "roa": doc.get("roa"),
            "gross_margin": doc.get("gross_margin"),
            "netprofit_margin": doc.get("netprofit_margin"),
            "peg": doc.get("peg"),
            "roic": doc.get("roic"),
            "asset_turnover": doc.get("asset_turnover"),
            "gross_profit_to_assets": doc.get("gross_profit_to_assets"),
            "interest_coverage": doc.get("interest_coverage"),
            "inventory_turnover": doc.get("inventory_turnover"),
            "receivable_turnover": doc.get("receivable_turnover"),
            "net_cash_position": doc.get("net_cash_position"),
            "piotroski_f_score": doc.get("piotroski_f_score"),
            "altman_z_score": doc.get("altman_z_score"),
            "beneish_m_score": doc.get("beneish_m_score"),
            "revenue_cagr_3y": doc.get("revenue_cagr_3y"),
            "profit_cagr_3y": doc.get("profit_cagr_3y"),
            "revenue_ttm": doc.get("revenue_ttm"),
            "revenue_yoy": doc.get("revenue_yoy"),
            "net_profit_ttm": doc.get("net_profit_ttm"),
            "net_profit_yoy": doc.get("net_profit_yoy"),
            "oper_profit_yoy": doc.get("oper_profit_yoy"),
            "n_cashflow_act": doc.get("n_cashflow_act"),
            "fcf": doc.get("fcf"),
            "fcf_yield": doc.get("fcf_yield"),
            "fcf_margin": doc.get("fcf_margin"),
            "ocf_yield": doc.get("ocf_yield"),
            "cash_conversion": doc.get("cash_conversion"),
            "accrual_ratio": doc.get("accrual_ratio"),
            "working_capital_change": doc.get("working_capital_change"),

            # Extended financial indicators (new calculated fields from stock_screening_view)
            "debt_to_assets": doc.get("debt_to_assets"),      # Asset-liability ratio (%)
            "assets_to_eqt": doc.get("assets_to_eqt"),        # equity multiplier
            "current_ratio": doc.get("current_ratio"),        # current ratio
            "quick_ratio": doc.get("quick_ratio"),            # quick ratio
            "cash_ratio": doc.get("cash_ratio"),              # cash ratio
            "dividend_yield": doc.get("dividend_yield"),      # dividend yield (%)
            "net_working_capital": doc.get("net_working_capital"),  # net working capital (billion)
            "is_st": doc.get("is_st"),                        # Whether ST shares
            "report_period": doc.get("report_period"),        # Latest financial reporting period

            # trading indicators
            "turnover_rate": doc.get("turnover_rate"),
            "volume_ratio": doc.get("volume_ratio"),

            # Transaction data (obtained from the view, which already contains real-time market data)
            "close": doc.get("close"),              # closing price
            "pct_chg": doc.get("pct_chg"),          # Increase or decrease(%)
            "amount": doc.get("amount"),            # Turnover
            "volume": doc.get("volume"),            # Volume
            "open": doc.get("open"),                # opening price
            "high": doc.get("high"),                # highest price
            "low": doc.get("low"),                  # lowest price

            # Technical Indicators (from Materialized Technology Snapshot)
            "ma20": doc.get("ma20"),
            "rsi14": doc.get("rsi14"),
            "kdj_k": doc.get("kdj_k"),
            "kdj_d": doc.get("kdj_d"),
            "kdj_j": doc.get("kdj_j"),
            "dif": doc.get("dif"),
            "dea": doc.get("dea"),
            "macd_hist": doc.get("macd_hist"),

            # metadata
            "source": doc.get("source", "database"),
            "updated_at": doc.get("updated_at"),
        }
        
        # Remove None value
        return {k: v for k, v in result.items() if v is not None}
    
    async def get_field_statistics(self, field: str) -> Dict[str, Any]:
        """
        Get field statistics
        
        Args:
            field: Field name
            
        Returns:
            Dict: Statistics {min, max, avg, count}
        """
        try:
            db_field = self.basic_fields.get(field)
            if not db_field:
                return {}
            
            db = get_mongo_db()
            # ⚠️ Performance fix: use stock_basic_info instead of stock_screening_view (view triggers $lookup Aggregation, query is extremely slow)
            collection = db["stock_basic_info"]
            
            # Get statistics using aggregation pipeline
            pipeline = [
                {"$match": {db_field: {"$exists": True, "$ne": None}}},
                {"$group": {
                    "_id": None,
                    "min": {"$min": f"${db_field}"},
                    "max": {"$max": f"${db_field}"},
                    "avg": {"$avg": f"${db_field}"},
                    "count": {"$sum": 1}
                }}
            ]
            
            result = await collection.aggregate(pipeline).to_list(length=1)
            
            if result:
                stats = result[0]
                avg_value = stats.get("avg")
                return {
                    "field": field,
                    "min": stats.get("min"),
                    "max": stats.get("max"),
                    "avg": round(avg_value, 2) if avg_value is not None else None,
                    "count": stats.get("count", 0)
                }
            
            return {"field": field, "count": 0}
            
        except Exception as e:
            logger.error(f"获取字段统计失败: {e}")
            return {"field": field, "error": str(e)}
    
    def _separate_conditions(self, conditions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Separate basic information conditions and real-time market conditions

        Args:
            conditions: All filters

        Returns:
            Tuple[List of basic information conditions, List of real-time market conditions]
        """
        # Real-time quotation field (need to be queried from market_quotes)
        quote_fields = {"pct_chg", "amount", "close", "volume"}

        basic_conditions = []
        quote_conditions = []

        for condition in conditions:
            field = condition.get("field") if isinstance(condition, dict) else condition.field
            if field in quote_fields:
                quote_conditions.append(condition)
            else:
                basic_conditions.append(condition)

        return basic_conditions, quote_conditions

    async def _enrich_with_quote_data(
        self,
        results: List[Dict[str, Any]],
        codes: List[str],
    ) -> None:
        """
        Supplement market data from market_quotes to the results in batches.
        Ensure close / pct_chg / amount / volume always has a value to display.
        """
        try:
            db = get_mongo_db()
            quotes_collection = db["market_quotes"]
            quotes_cursor = quotes_collection.find({"code": {"$in": codes}})
            quotes_map: Dict[str, Dict[str, Any]] = {}
            async for quote in quotes_cursor:
                code = quote.get("code")
                if code:
                    quotes_map[code] = {
                        "close": quote.get("close"),
                        "pct_chg": quote.get("pct_chg"),
                        "amount": quote.get("amount"),
                        "volume": quote.get("volume"),
                        "open": quote.get("open"),
                        "high": quote.get("high"),
                        "low": quote.get("low"),
                        "pre_close": quote.get("pre_close"),
                        "trade_date": quote.get("trade_date"),
                    }

            for result in results:
                code = result.get("code")
                qd = quotes_map.get(code)
                if qd:
                    for k, v in qd.items():
                        if v is not None and result.get(k) is None:
                            result[k] = v

            logger.debug(f"✅ 行情数据补充完成: {len(quotes_map)}/{len(codes)} 只股票有行情")
        except Exception as e:
            logger.warning(f"⚠️ 补充行情数据失败: {e}")

    def _apply_quote_filter(
        self,
        results: List[Dict[str, Any]],
        quote_conditions: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Filter results according to quotation conditions in memory (results have been supplemented with quotations through _enrich_with_quote_data)"""
        filtered = []
        for result in results:
            match = True
            for condition in quote_conditions:
                field = condition.get("field") if isinstance(condition, dict) else condition.field
                operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
                value = condition.get("value") if isinstance(condition, dict) else condition.value

                field_value = result.get(field)
                if field_value is None:
                    match = False
                    break

                if operator == "between" and isinstance(value, list) and len(value) == 2:
                    if not (value[0] <= field_value <= value[1]):
                        match = False
                elif operator == ">":
                    if not (field_value > value):
                        match = False
                elif operator == "<":
                    if not (field_value < value):
                        match = False
                elif operator == ">=":
                    if not (field_value >= value):
                        match = False
                elif operator == "<=":
                    if not (field_value <= value):
                        match = False
                elif operator == "==":
                    if field_value != value:
                        match = False
                elif operator == "!=":
                    if field_value == value:
                        match = False

                if not match:
                    break

            if match:
                filtered.append(result)
        return filtered

    async def _filter_by_quotes(
        self,
        results: List[Dict[str, Any]],
        codes: List[str],
        quote_conditions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Secondary screening based on real-time market data

        Args:
            results: Initial screening results
            codes: Stock code list
            quote_conditions: Real-time market filter conditions

        Returns:
            List[Dict]: Filtered results
        """
        try:
            db = get_mongo_db()
            quotes_collection = db['market_quotes']

            # Query real-time market data in batches
            quotes_cursor = quotes_collection.find({"code": {"$in": codes}})
            quotes_map = {}
            async for quote in quotes_cursor:
                code = quote.get("code")
                quotes_map[code] = {
                    "close": quote.get("close"),
                    "pct_chg": quote.get("pct_chg"),
                    "amount": quote.get("amount"),
                    "volume": quote.get("volume"),
                }

            logger.info(f"📊 查询到 {len(quotes_map)} 只股票的实时行情数据")

            # Filter results
            filtered_results = []
            for result in results:
                code = result.get("code")
                quote_data = quotes_map.get(code)

                if not quote_data:
                    # There is no real-time market data, skip it
                    continue

                # Check whether all real-time market conditions are met
                match = True
                for condition in quote_conditions:
                    field = condition.get("field") if isinstance(condition, dict) else condition.field
                    operator = condition.get("operator") if isinstance(condition, dict) else condition.operator
                    value = condition.get("value") if isinstance(condition, dict) else condition.value

                    field_value = quote_data.get(field)
                    if field_value is None:
                        match = False
                        break

                    # Check conditions
                    if operator == "between" and isinstance(value, list) and len(value) == 2:
                        if not (value[0] <= field_value <= value[1]):
                            match = False
                            break
                    elif operator == ">":
                        if not (field_value > value):
                            match = False
                            break
                    elif operator == "<":
                        if not (field_value < value):
                            match = False
                            break
                    elif operator == ">=":
                        if not (field_value >= value):
                            match = False
                            break
                    elif operator == "<=":
                        if not (field_value <= value):
                            match = False
                            break

                if match:
                    # Incorporate real-time market data into results
                    result.update(quote_data)
                    filtered_results.append(result)

            logger.info(f"✅ 实时行情筛选完成: 筛选前={len(results)}, 筛选后={len(filtered_results)}")
            return filtered_results

        except Exception as e:
            logger.error(f"❌ 实时行情筛选失败: {e}")
            # If it fails, return the original result
            return results

    async def get_available_values(self, field: str, limit: int = 100) -> List[str]:
        """
        Get a list of optional values for a field (for enumeration type fields)
        
        Args:
            field: Field name
            limit: Return quantity limit
            
        Returns:
            List[str]: list of optional values
        """
        try:
            db_field = self.basic_fields.get(field)
            if not db_field:
                return []
            
            db = get_mongo_db()
            # ⚠️ Performance fix: use stock_basic_info instead of stock_screening_view (view triggers $lookup Aggregation, query is extremely slow)
            collection = db["stock_basic_info"]
            
            # Get unique values of a field
            values = await collection.distinct(db_field)
            
            # Filter None values and sort
            values = [v for v in values if v is not None]
            values.sort()
            
            return values[:limit]
            
        except Exception as e:
            logger.error(f"获取字段可选值失败: {e}")
            return []


# Global service instance
_database_screening_service: Optional[DatabaseScreeningService] = None


def get_database_screening_service() -> DatabaseScreeningService:
    """获取数据库筛选服务实例"""
    global _database_screening_service
    if _database_screening_service is None:
        _database_screening_service = DatabaseScreeningService()
    return _database_screening_service

# === intelligent_screening_service.py ===
"""
Intelligent screening service — LLM Multiple rounds of dialogue stock selection

Reuse the LLM configuration, tool registry, timeout mechanism and other infrastructure of the intelligent assistant,
Added two-stage process (requirement confirmation → perform screening) and multiple rounds of memorization.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object

# Reuse the infrastructure of smart assistants
from app.services.intelligent_assistant_service import (
    _get_assistant_llm_config,
    _get_latest_trade_date,
    ASSISTANT_TIMEOUT_SECONDS,
)
from core.tools import get_tool_registry, tool_metadata_list_to_openai
from core.tools.context import set_current_user_id
from core.tools.implementations.market.stock_screening_tool import _execute_screening_query, _format_screening_output
from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

# Maximum number of session history items (per user)
SCREENING_CONVERSATION_LIMIT = 50
# The maximum number of historical messages sent to LLM per request
MAX_CONTEXT_MESSAGES = 20
# Tool categories related to stock picking
# "screening" Category Contains screen_stocks_by_criteria Batch Filter Tool (Core)
SCREENING_TOOL_CATEGORIES = ["screening", "market", "fundamentals", "news", "china", "technical"]
SCREENING_TOOL_IDS = {
    "add_stocks_to_favorites",
    "list_watchlist_groups",
    "add_stock_to_watchlist",
}

# Tool convergence in the execution phase: Prioritize only allowing batch screening of links to avoid single-strand heavy tool amplification delays
RESULT_TOOL_ALLOWLIST = {
    "screen_stocks_by_criteria",
    "batch_check_profit_consistency",
    "add_stocks_to_favorites",
    "list_watchlist_groups",
    "add_stock_to_watchlist",
}

# Independent budget for stock selection scenarios, tighter than the global assistant by default, to avoid long-tail requests from dragging down the experience
SCREENING_MAX_TOOL_ROUNDS = int(os.environ.get("SCREENING_MAX_TOOL_ROUNDS", "3"))
SCREENING_RESULT_TIMEOUT_SECONDS = int(os.environ.get("SCREENING_RESULT_TIMEOUT_SECONDS", "300"))

SCREENING_ADJUST_KEYWORDS = [
    "重新",
    "修改",
    "调整需求",
    "换个",
    "不对",
    "重新描述",
    "重新考虑",
    "再低点",
    "再高点",
    "缩小",
    "放宽",
]

SCREENING_APPROVAL_KEYWORDS = [
    "执行筛选方案",
    "按此方案",
    "开始筛选",
    "执行",
    "同意",
    "确认",
    "按原需求筛选",
]

SCREENING_NEW_REQUEST_KEYWORDS = [
    "帮我选",
    "选几只",
    "筛选",
    "选股",
    "推荐几只",
    "找几只",
    "高分红",
    "低估值",
    "股票",
]

SCREENING_RESULT_REFERENCE_KEYWORDS = [
    "这5只",
    "这五只",
    "这几只",
    "这些股票",
    "刚才那5只",
    "刚才推荐",
    "当前推荐",
    "上一轮",
    "加入自选",
    "加入股票关注列表",
    "打标签",
    "分组",
]

SCREENING_MULTI_STOCK_REQUEST_KEYWORDS = [
    "帮我选",
    "筛选",
    "推荐几只",
    "找几只",
    "候选",
    "组合",
]

SINGLE_STOCK_QUERY_PREFIXES = (
    "请问一下",
    "请问",
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "帮我看下",
    "帮我判断一下",
    "麻烦看下",
    "麻烦问下",
)

SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD = 3.0

SCREENING_FIELD_DISPLAY_LABELS = {
    "industry": "行业",
    "dividend_yield": "股息率",
    "pe": "PE",
    "pe_ttm": "PE(TTM)",
    "pb": "PB",
    "pb_mrq": "PB(MRQ)",
    "roe": "ROE",
    "roa": "ROA",
    "gross_margin": "毛利率",
    "netprofit_margin": "净利率",
    "debt_to_assets": "资产负债率",
    "assets_to_eqt": "权益乘数",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "cash_ratio": "现金比率",
    "total_mv": "总市值",
    "close": "股价",
    "pct_chg": "涨跌幅",
    "report_period": "财报期",
    "n_cashflow_act": "经营现金流",
    "revenue_ttm": "营收TTM",
    "net_profit_ttm": "净利TTM",
}

SCREENING_PERCENT_FIELDS = {
    "dividend_yield",
    "roe",
    "roa",
    "gross_margin",
    "netprofit_margin",
    "debt_to_assets",
    "pct_chg",
}

SCREENING_YI_FIELDS = {"n_cashflow_act", "revenue_ttm", "net_profit_ttm"}


class IntelligentScreeningService:
    """
    Intelligent screening service — LLM Multiple rounds of dialogue stock selection

    Reuse the LLM configuration, tool registry, timeout mechanism and other infrastructure of the intelligent assistant,
    Added two-stage process (requirement confirmation → perform screening) and multiple rounds of memorization.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._openai_tools: Optional[list] = None
        self._result_openai_tools: Optional[list] = None
        self._tool_functions: Optional[dict] = None

    async def _ensure_client(self) -> bool:
        """Lazy loading of LLM clients and tools (only 5 types of tools related to stock selection are loaded)"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(self._db)
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
        except Exception as e:
            logger.error(f"[Smart filtering] Creating LLM client failed: {e}", exc_info=True)
            return False

        # Only load tools related to stock selection
        registry = get_tool_registry()
        all_metadata = registry.list_all()
        screening_metadata = [
            m for m in all_metadata
            if m.fc_enabled and (m.category in SCREENING_TOOL_CATEGORIES or m.id in SCREENING_TOOL_IDS)
        ]
        self._openai_tools = tool_metadata_list_to_openai(screening_metadata)

        self._tool_functions = {}
        for tool in screening_metadata:
            if tool.parameters:
                func = registry.get_function(tool.id)
                if func:
                    self._tool_functions[tool.id] = func

        # In the results execution phase, only tools related to batch screening are retained to limit the complexity of the tool chain.
        self._result_openai_tools = self._filter_result_tools(self._openai_tools)
        if not self._result_openai_tools:
            self._result_openai_tools = self._openai_tools
            logger.warning("[Smart filtering] In the result stage, the batch tool whitelist is empty and falls back to the complete tool set.")

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(
            f"[智能筛选] 已加载 {len(self._openai_tools)} 个选股工具，"
            f"Used in the results phase {len(self._result_openai_tools)} execution tools"
        )
        return True

    def _filter_result_tools(self, openai_tools: Optional[list]) -> list:
        """The tools available in the filtering result stage give priority to retaining batch filtering links."""
        if not openai_tools:
            return []

        filtered = []
        for t in openai_tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            name = fn.get("name")
            if name in RESULT_TOOL_ALLOWLIST:
                filtered.append(t)
        return filtered

    def _infer_request_focus(self, message: str) -> str:
        """Extract core filtering requirements from user requests for no-result and downgrade prompts."""
        text = (message or "").strip()
        if not text:
            return "原筛选条件"

        focus_keywords = [
            ("高分红", ["高分红", "分红", "股息", "股息率", "dividend"]),
            ("低估值", ["低估值", "低pe", "低 pb", "低pb", "估值低", "便宜"]),
            ("银行股", ["银行"]),
            ("消费股", ["消费"]),
            ("科技股", ["科技", "芯片", "半导体", "ai"]),
            ("高ROE", ["roe"]),
        ]
        lower_text = text.lower()
        for label, keywords in focus_keywords:
            if any(keyword in text or keyword in lower_text for keyword in keywords):
                return label
        return "原筛选条件"

    def _extract_single_stock_keyword(self, message: str) -> Optional[str]:
        """Extract stock symbols or abbreviations from single stock judgment questions."""
        text = re.sub(r"\s+", "", message or "")
        if not text:
            return None

        code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        if code_match:
            return code_match.group(1)

        normalized = text
        for prefix in SINGLE_STOCK_QUERY_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        normalized = re.sub(r"[？?！!。,.，：:；;]", "", normalized)
        patterns = [
            r"([A-Za-z\u4e00-\u9fa5]{2,16})(?:\(| ()?(?:\d{6})?(?:\)|) )?(?:Isn t it|Whether|Does it count?|does not belong to|Belong to|Yes)",
            r"([A-Za-z\u4e00-\u9fa5]{2,16})(?:\(| ()?(?:\d{6})?(?:\)|) )?(?:of)?(?:dividend yield|dividend)",
        ]
        stopwords = {"这个", "这只", "该股", "股票", "A股", "个股"}
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            keyword = match.group(1).strip()
            if keyword in stopwords or len(keyword) < 2:
                continue
            return keyword

        return None

    def _looks_like_single_stock_judgement_query(self, message: str) -> bool:
        """identify Whether a single stock meets a certain attribute of direct judgment."""
        text = re.sub(r"\s+", "", message or "")
        if not text:
            return False

        if self._is_adjustment_message(text) or self._is_approval_message(text):
            return False

        if any(keyword in text for keyword in SCREENING_MULTI_STOCK_REQUEST_KEYWORDS):
            return False

        if self._infer_request_focus(text) != "高分红":
            return False

        if not self._extract_single_stock_keyword(text):
            return False

        return any(token in text for token in ("是不是", "是否", "算不算", "属于", "是", "吗"))

    async def _fetch_single_stock_item(self, keyword: str) -> Optional[dict]:
        """Retrieve the best matching single stock snapshot by symbol or name."""
        items, _total = await _execute_screening_query(
            [{"field": "keyword", "operator": "contains", "value": keyword}],
            10,
            "total_mv",
            "desc",
        )
        if not items:
            return None

        normalized = keyword.strip().lower()

        def score(item: dict) -> tuple[int, float]:
            code = str(item.get("code") or item.get("symbol") or "").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            item_score = 0
            if normalized == code:
                item_score += 100
            if normalized == name:
                item_score += 95
            if normalized and normalized in name:
                item_score += 80
            if normalized and normalized in code:
                item_score += 70
            return item_score, float(item.get("total_mv") or 0)

        return max(items, key=score)

    def _build_single_stock_snapshot(self, item: dict, reason: str) -> dict[str, Any]:
        pe_order_field = "pe_ttm" if item.get("pe_ttm") is not None else "pe"
        pb_order_field = "pb_mrq" if item.get("pb_mrq") is not None else "pb"
        pe_display_field, pe_display_label = select_metric_display_spec(None, pe_order_field, "pe")
        pb_display_field, pb_display_label = select_metric_display_spec(None, pb_order_field, "pb")
        code = str(item.get("code") or item.get("symbol") or "").strip()

        return {
            "code": code,
            "name": str(item.get("name") or ""),
            "industry": str(item.get("industry") or ""),
            "price": item.get("close"),
            "pe": resolve_metric_value(item, pe_display_field, "pe"),
            "pe_display_label": pe_display_label,
            "pb": resolve_metric_value(item, pb_display_field, "pb"),
            "pb_display_label": pb_display_label,
            "roe": item.get("roe"),
            "roa": item.get("roa"),
            "gross_margin": item.get("gross_margin"),
            "netprofit_margin": item.get("netprofit_margin"),
            "dividend_yield": item.get("dividend_yield"),
            "debt_to_assets": item.get("debt_to_assets"),
            "assets_to_eqt": item.get("assets_to_eqt"),
            "current_ratio": item.get("current_ratio"),
            "quick_ratio": item.get("quick_ratio"),
            "cash_ratio": item.get("cash_ratio"),
            "revenue_ttm": item.get("revenue_ttm"),
            "net_profit_ttm": item.get("net_profit_ttm"),
            "n_cashflow_act": item.get("n_cashflow_act"),
            "report_period": item.get("report_period"),
            "pct_change": item.get("pct_chg"),
            "reason": reason,
        }

    async def _maybe_handle_single_stock_query(
        self,
        message: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Directly return results for single stock attribute judgment questions to avoid entering the market-wide screening process by mistake."""
        if not self._looks_like_single_stock_judgement_query(message):
            return None

        await self._emit_progress(
            progress_callback,
            "status",
            phase="result",
            message="Checking the dividend index of a single stock",
        )

        keyword = self._extract_single_stock_keyword(message)
        if not keyword:
            return None

        item = await self._fetch_single_stock_item(keyword)
        if not item:
            reply = f"未找到与“{keyword}”匹配的股票，暂时无法判断它是否属于高分红股票。"
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "is_fallback": False,
            }

        stock_name = str(item.get("name") or keyword)
        stock_code = str(item.get("code") or item.get("symbol") or "")
        dividend_yield = item.get("dividend_yield")
        if not isinstance(dividend_yield, (int, float)):
            reply = f"已找到 {stock_name}（{stock_code}），但当前快照里没有可用的股息率数据，暂时无法判断它是否属于高分红股票。"
            stock = self._build_single_stock_snapshot(item, "There is currently a lack of available dividend yield data, so it is impossible to directly determine whether it is a high dividend payout.")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [stock],
                "phase": "result",
                "is_fallback": False,
            }

        is_high_dividend = dividend_yield >= SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD
        verdict = "可以算" if is_high_dividend else "严格按当前默认口径暂不算"
        reason = (
            f"Single stock verification: the default is based on the dividend rate of the past 12 months ≥ {SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD:.1f}% As a high dividend caliber;"
            f"current dividend yield={dividend_yield:.2f}%, Therefore{verdict}High dividends."
        )
        stock = self._build_single_stock_snapshot(item, reason)

        metrics: list[str] = [f"股息率={dividend_yield:.2f}%"]
        if isinstance(stock.get("pe"), (int, float)):
            metrics.append(f"{stock.get('pe_display_label') or 'PE'}={stock['pe']:.2f}")
        if isinstance(stock.get("roe"), (int, float)):
            metrics.append(f"ROE={stock['roe']:.2f}%")
        if stock.get("report_period"):
            metrics.append(f"财报期={stock['report_period']}")

        reply_lines = [
            f"Conclusion:{stock_name} ({stock_code}) {verdict}High dividend stocks.",
            f"Judgment criteria: If no additional threshold is specified, this system defaults to the dividend rate of the past 12 months ≥ {SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD:.1f}% Considered a high dividend.",
            f"Current indicators:{'; '.join(metrics)}. ",
        ]
        if is_high_dividend:
            reply_lines.append("Additional explanation: It is closer to a high-quality white horse that pays stable dividends, and is not the same as a dividend target with the highest dividend yield in the market.")
        else:
            reply_lines.append("Supplementary note: If you are more concerned about dividend stability or dividend ratio rather than the static dividend rate threshold, you can use this caliber to make your judgment.")

        return {
            "reply": "\n\n".join(reply_lines),
            "tools_used": [],
            "stocks": [stock],
            "phase": "result",
            "is_fallback": False,
        }

    def _build_no_match_reply(self, message: str) -> str:
        """A hard tip is returned when the condition is not hit, and no alternative stocks are recommended."""
        focus = self._infer_request_focus(message)
        return (
            f"未找到符合“{focus}”条件的股票。\n\n"
            "There is currently no target that meets the screening requirements, and other stocks that do not meet the conditions are not recommended."
            "If you still want to continue filtering, please further add thresholds, narrow the industry scope, or adjust the filtering conditions and try again."
        )

    def _build_timeout_reply(self, timeout_seconds: int) -> str:
        """A hard prompt is returned when execution times out and no alternative stocks are recommended."""
        return (
            f"Sorry, processing your stock selection request has timed out (more than {timeout_seconds} seconds).\n\n"
            "This time we will not recommend other stocks that do not meet the original screening conditions."
            "It is recommended that you narrow the filter scope, add more specific thresholds or industry conditions, or try again later."
        )

    def _find_last_assistant(self, history: list) -> Optional[dict]:
        for msg in reversed(history or []):
            if msg.get("role") == "assistant":
                return msg
        return None

    async def _classify_intent(self, message: str, history: list) -> Dict[str, Any]:
        """
        Let LLM analyze user intent instead of hard-coding keywords.

        Return:
        {
            "intent": "adjustment" | "approval" | "new_request" | "follow_up" | "single_stock_query",
            "adjustment_target": "roe" | "pe" | "pb" | "margin" | "other" | null,
            "adjustment_direction": "loosen" | "tighten" | null,
            "explicit_parameters": str | null,
            "confidence": float
        }
        """
        if not await self._ensure_client():
            # If LLM is not available, fall back to keyword mode
            return {
                "intent": "adjustment" if self._is_adjustment_message(message) else
                          "approval" if self._is_approval_message(message) else
                          "new_request" if self._looks_like_new_screening_request(message) else
                          "single_stock_query" if self._looks_like_single_stock_judgement_query(message) else
                          "follow_up",
                "adjustment_target": None,
                "adjustment_direction": None,
                "explicit_parameters": None,
                "confidence": 0.5
            }

        history_summary = ""
        if history:
            recent = history[-4:]  # The last 4 items are enough to understand the context
            for h in recent:
                role = "用户" if h["role"] == "user" else "助手"
                content = h["content"][:200] + "..." if len(h["content"]) > 200 else h["content"]
                history_summary += f"{role}: {content}\n"

        system_prompt = """You are an intent classifier. Please analyze the user s latest news and combine it with the conversation history to determine the user s intention.

Return JSON format:
{
    "intent": "adjustment" | "approval" | "new_request" | "follow_up" | "single_stock_query",
    "adjustment_target": "roe" | "pe" | "pb" | "margin" | "debt" | "cashflow" | "other" | null,
    "adjustment_direction": "loosen" | "tighten" | null,
    "explicit_parameters": "Specific parameters explicitly mentioned by the user, e.g.'Relax ROE to 10%'in'10%'" | null,
    "confidence": 0.0-1.0 confidence level between
}

Intent definition:
- adjustment: The user wants to adjust the previous filtering conditions (relax, tighten, modify, etc.)
- approval: The user explicitly approves a plan ("execute", "According to this plan", "OK"etc.)
- new_request: Users have put forward new stock selection needs, which have little to do with the previous screening.
- follow_up: The user asks based on the current results ("How about these ones?", "Add to your choice"etc.)
- single_stock_query: User asks about a single stock

adjustment_target: When intent=adjustment, indicate which indicator the user wants to adjust
adjustment_direction: When intent=adjustment when it is pointed out that it is relaxing(loosen)Still tighten(tighten)

Note:
- If the user says"Let s relax ROE first", intent=adjustment, adjustment_target=roe, adjustment_direction=loosen
- If the user says"Change PE to<20", intent=adjustment, adjustment_target=pe, adjustment_direction=loosen, explicit_parameters="20"
- If the user says"Execute screening plan", intent=approval
- If the user says"Help me choose technology stocks again", intent=new_request
- If the user says"Add these to your choice", intent=follow_up
- If the user asks"How about Kweichow Moutai?", intent=single_stock_query
"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=f"Conversation history:\n{history_summary}\n\n Latest user news:{message}")
        ]

        try:
            resp = await self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="intent_classification")
            content = resp.content if resp else ""
            # Extract JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group(0))
                return result
        except Exception as e:
            logger.warning(f"[Smart filtering] Intent classification LLM call failed: {e}")

        # Fallback on failure
        return {
            "intent": "adjustment" if self._is_adjustment_message(message) else
                      "approval" if self._is_approval_message(message) else
                      "new_request" if self._looks_like_new_screening_request(message) else
                      "single_stock_query" if self._looks_like_single_stock_judgement_query(message) else
                      "follow_up",
            "adjustment_target": None,
            "adjustment_direction": None,
            "explicit_parameters": None,
            "confidence": 0.3
        }

    def _is_adjustment_message(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_ADJUST_KEYWORDS)

    def _is_approval_message(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_APPROVAL_KEYWORDS)

    def _looks_like_new_screening_request(self, message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False
        if self._is_adjustment_message(text) or self._is_approval_message(text):
            return False
        return any(keyword in text for keyword in SCREENING_NEW_REQUEST_KEYWORDS)

    def _references_latest_result(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_RESULT_REFERENCE_KEYWORDS)

    def _select_phase_history(self, history: list, phase: str, message: str, intent: Dict[str, Any] = None) -> list:
        """Compress history by stage to avoid the result stage continuing to inherit the entire old session."""
        recent_history = history[-MAX_CONTEXT_MESSAGES:]
        if not recent_history:
            return []

        # If it is an adjustment class, approval class, or follow-up message, keep the full history so LLM understands the context
        intent_type = intent.get("intent") if intent else None
        if intent_type in ["adjustment", "approval", "follow_up"]:
            return recent_history

        last_assistant = self._find_last_assistant(recent_history)
        if (
            phase == "confirmation"
            and last_assistant
            and last_assistant.get("phase") == "result"
            and intent_type == "new_request"
        ):
            return []

        if phase != "result":
            return recent_history

        selected_history: List[dict] = []
        latest_planning = None
        latest_result = None
        for item in reversed(recent_history):
            if item.get("role") != "assistant":
                continue
            item_phase = item.get("phase")
            if latest_result is None and item_phase == "result":
                latest_result = item
            if latest_planning is None and item_phase == "planning":
                latest_planning = item
            if latest_planning and latest_result:
                break

        if latest_planning:
            selected_history.append(latest_planning)
        if latest_result and intent_type == "follow_up":
            selected_history.append(latest_result)

        return selected_history or recent_history[-2:]

    def _extract_locked_execution_plan(self, history: list) -> Optional[dict]:
        """Extract approved batch execution parameters from the most recent planning reply."""
        latest_planning = None
        for item in reversed(history or []):
            if item.get("role") == "assistant" and item.get("phase") == "planning":
                latest_planning = item
                break

        if not latest_planning:
            return None

        content = str(latest_planning.get("content") or "")
        conditions_match = re.search(r"`?conditions`?\s*[:：]\s*`(\[[\s\S]*?\])`", content)
        limit_match = re.search(r"`?limit`?\s*[:：]\s*(\d+)", content)
        order_by_match = re.search(r'`?order_by_field`?\s*[:：]\s*"([^"]+)"', content)
        order_direction_match = re.search(r'`?order_direction`?\s*[:：]\s*"([^"]+)"', content)

        if not conditions_match:
            return None

        try:
            raw_conditions = json.loads(conditions_match.group(1))
        except json.JSONDecodeError:
            return None

        if not isinstance(raw_conditions, list) or not raw_conditions:
            return None

        plan: Dict[str, Any] = {
            "planning_content": content,
            "screen": {
                "conditions_json": json.dumps(raw_conditions, ensure_ascii=False),
                "limit": int(limit_match.group(1)) if limit_match else 50,
                "order_by_field": order_by_match.group(1) if order_by_match else "total_mv",
                "order_direction": order_direction_match.group(1) if order_direction_match else "desc",
            },
        }

        years_match = re.search(r"`?years`?\s*[:：]\s*(\d+)", content)
        threshold_match = re.search(r"`?threshold_cv`?\s*[:：]\s*([0-9.]+)", content)
        if years_match or threshold_match:
            plan["batch"] = {
                "years": int(years_match.group(1)) if years_match else 3,
                "threshold_cv": float(threshold_match.group(1)) if threshold_match else 0.3,
            }

        return plan

    def _extract_candidate_codes(self, screening_output: str) -> list[str]:
        match = re.search(r"Candidate code list (sorted by current, total\s*\d+\s*only):\s*([^\n]+)", screening_output or "")
        if not match:
            return []
        return [code.strip() for code in match.group(1).split(",") if code.strip()]

    def _build_locked_plan_summary(self, locked_plan: dict) -> str:
        screen_plan = locked_plan.get("screen", {})
        try:
            conditions = json.loads(screen_plan.get("conditions_json", "[]"))
        except json.JSONDecodeError:
            conditions = []

        lines = ["Summary of approved execution plan:"]
        if conditions:
            lines.append(f"- 筛选条件: {json.dumps(conditions, ensure_ascii=False)}")
        lines.append(f"- limit: {screen_plan.get('limit', 50)}")
        lines.append(f"- order_by_field: {screen_plan.get('order_by_field', 'total_mv')}")
        lines.append(f"- order_direction: {screen_plan.get('order_direction', 'desc')}")

        batch_plan = locked_plan.get("batch")
        if batch_plan:
            lines.append(
                f"- Profit stability verification: years={batch_plan.get('years', 3)}, "
                f"threshold_cv={batch_plan.get('threshold_cv', 0.3)}"
            )

        return "\n".join(lines)

    def _compact_screening_output_for_llm(self, screening_output: str) -> str:
        lines = [line for line in (screening_output or "").splitlines() if line.strip()]
        if not lines:
            return "No filter results."

        summary_lines: List[str] = [lines[0]]
        candidate_lines = [line for line in lines if re.match(r"^\d+\.\s", line)]
        summary_lines.extend(candidate_lines[:5])
        if len(candidate_lines) > 5:
            summary_lines.append(f"其余 {len(candidate_lines) - 5} 只候选已省略。")
        return "\n".join(summary_lines)

    def _compact_batch_output_for_llm(self, batch_output: str) -> str:
        lines = [line for line in (batch_output or "").splitlines() if line.strip()]
        if not lines:
            return "No profit stability verification was performed in this round."

        summary_lines = [lines[0]]
        summary_match = next((line for line in lines if line.startswith("📊 Summary:")), "")
        if summary_match:
            summary_lines.append(summary_match)

        stable_match = re.search(r"✅ Stable stock code:([^\n]+)", batch_output or "")
        if stable_match:
            stable_codes = [code.strip() for code in stable_match.group(1).split(",") if code.strip()]
            preview = ", ".join(stable_codes[:8])
            summary_lines.append(f"稳定股票代码预览: {preview}")
            if len(stable_codes) > 8:
                summary_lines.append(f"其余 {len(stable_codes) - 8} 只稳定股票代码已省略。")

        no_data_match = re.search(r"No data\s*(\d+)\s*only", batch_output or "")
        if no_data_match:
            summary_lines.append(f"无数据股票数量: {no_data_match.group(1)}")

        return "\n".join(summary_lines)

    def _extract_stable_codes(self, batch_output: str) -> list[str]:
        stable_match = re.search(r"✅ Stable stock code:([^\n]+)", batch_output or "")
        if not stable_match:
            return []
        return [code.strip() for code in stable_match.group(1).split(",") if code.strip()]

    def _format_reason_metric_value(self, field: str, value: Any) -> str:
        if value is None:
            return "-"
        if field in SCREENING_PERCENT_FIELDS and isinstance(value, (int, float)):
            return f"{value:.2f}%"
        if field in SCREENING_YI_FIELDS and isinstance(value, (int, float)):
            return f"{value / 1e8:.2f}亿"
        if field == "total_mv" and isinstance(value, (int, float)):
            return f"{value:.2f}亿"
        if field == "report_period":
            return str(value)
        if isinstance(value, (int, float)):
            return f"{value:.2f}"
        return str(value)

    def _get_reason_field_label(self, field: str, pe_display_label: str, pb_display_label: str) -> str:
        if field in {"pe", "pe_ttm"}:
            return pe_display_label
        if field in {"pb", "pb_mrq"}:
            return pb_display_label
        return SCREENING_FIELD_DISPLAY_LABELS.get(field, field)

    def _build_stock_reason(
        self,
        item: dict,
        raw_conditions: list,
        pe_display_field: str,
        pe_display_label: str,
        pb_display_field: str,
        pb_display_label: str,
        stability_checked: bool,
        stability_passed: bool,
    ) -> str:
        reason_parts: list[str] = []
        seen_parts: set[str] = set()

        for condition in raw_conditions:
            if not isinstance(condition, dict):
                continue
            field = condition.get("field")
            if field == "is_st" and condition.get("value") is False:
                if "非ST" not in seen_parts:
                    reason_parts.append("非ST")
                    seen_parts.add("非ST")
                continue

            if field == "keyword":
                continue

            if field in {"pe", "pe_ttm"}:
                value = resolve_metric_value(item, pe_display_field, "pe")
            elif field in {"pb", "pb_mrq"}:
                value = resolve_metric_value(item, pb_display_field, "pb")
            else:
                value = item.get(field)

            if value is None:
                continue

            label = self._get_reason_field_label(field, pe_display_label, pb_display_label)
            part = f"{label}={self._format_reason_metric_value(field, value)}"
            if part not in seen_parts:
                reason_parts.append(part)
                seen_parts.add(part)

        if not reason_parts:
            fallback_fields = [
                (pe_display_field, pe_display_label),
                (pb_display_field, pb_display_label),
                ("dividend_yield", "股息率"),
                ("roe", "ROE"),
                ("debt_to_assets", "资产负债率"),
            ]
            for field, label in fallback_fields:
                value = resolve_metric_value(item, field, "pe") if field in {"pe", "pe_ttm"} else resolve_metric_value(item, field, "pb") if field in {"pb", "pb_mrq"} else item.get(field)
                if value is None:
                    continue
                part = f"{label}={self._format_reason_metric_value(field, value)}"
                if part not in seen_parts:
                    reason_parts.append(part)
                    seen_parts.add(part)

        report_period = item.get("report_period")
        if report_period and "财报期" not in seen_parts:
            reason_parts.append(f"财报期={report_period}")

        if stability_checked:
            reason_parts.append("近3年盈利稳定性验证通过" if stability_passed else "This round was not included in the profit stability pass list")

        if not reason_parts:
            return "Matches approved filters."

        return "Meet approved conditions:" + "，".join(reason_parts[:5]) + "。"

    def _build_structured_stocks(
        self,
        items: list,
        raw_conditions: list,
        order_by_field: str,
        batch_output: str,
    ) -> list[dict[str, Any]]:
        pe_display_field, pe_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pe")
        pb_display_field, pb_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pb")
        stable_codes = self._extract_stable_codes(batch_output)
        stable_set = set(stable_codes)
        selected_items = items or []
        if stable_codes:
            stable_items = [
                item for item in selected_items
                if str(item.get("code") or item.get("symbol", "")).strip() in stable_set
            ]
            if stable_items:
                selected_items = stable_items

        stocks: list[dict[str, Any]] = []
        for item in selected_items[:5]:
            code = str(item.get("code") or item.get("symbol", "")).strip()
            if not code:
                continue

            stability_checked = bool(batch_output)
            stability_passed = code in stable_set if stable_set else False
            stocks.append({
                "code": code,
                "name": str(item.get("name") or ""),
                "industry": str(item.get("industry") or ""),
                "price": item.get("close"),
                "pe": resolve_metric_value(item, pe_display_field, "pe"),
                "pe_display_label": pe_display_label,
                "pb": resolve_metric_value(item, pb_display_field, "pb"),
                "pb_display_label": pb_display_label,
                "roe": item.get("roe"),
                "roa": item.get("roa"),
                "gross_margin": item.get("gross_margin"),
                "netprofit_margin": item.get("netprofit_margin"),
                "dividend_yield": item.get("dividend_yield"),
                "debt_to_assets": item.get("debt_to_assets"),
                "assets_to_eqt": item.get("assets_to_eqt"),
                "current_ratio": item.get("current_ratio"),
                "quick_ratio": item.get("quick_ratio"),
                "cash_ratio": item.get("cash_ratio"),
                "revenue_ttm": item.get("revenue_ttm"),
                "net_profit_ttm": item.get("net_profit_ttm"),
                "n_cashflow_act": item.get("n_cashflow_act"),
                "report_period": item.get("report_period"),
                "pct_change": item.get("pct_chg"),
                "reason": self._build_stock_reason(
                    item,
                    raw_conditions,
                    pe_display_field,
                    pe_display_label,
                    pb_display_field,
                    pb_display_label,
                    stability_checked,
                    stability_passed,
                ),
            })

        return stocks

    def _build_locked_result_reply(self, total_candidates: int, stocks: list[dict[str, Any]], batch_output: str) -> str:
        lines = ["The approved screening plan has been implemented."]
        if total_candidates:
            lines.append(f"共筛出 {total_candidates} 只候选。")

        batch_summary = next(
            (line.strip() for line in (batch_output or "").splitlines() if line.strip().startswith("📊 Summary:")),
            "",
        )
        if batch_summary:
            lines.append(batch_summary)

        if not stocks:
            if batch_output:
                lines.append("There were candidates in the original screening, but after verification of profitability stability, no final list was formed, and the threshold will no longer be relaxed.")
            else:
                lines.append("No final candidates have been formed to be displayed, and the threshold will no longer be relaxed.")
        else:
            if len(stocks) < 5:
                lines.append(f"当前仅有 {len(stocks)} 只候选满足条件，不再放宽阈值。")
            else:
                lines.append("The following are the 5 candidates that best meet the current conditions:")

            for index, stock in enumerate(stocks, 1):
                metrics = []
                if isinstance(stock.get("price"), (int, float)):
                    metrics.append(f"价格={stock['price']:.2f}元")
                if isinstance(stock.get("pe"), (int, float)):
                    metrics.append(f"{stock.get('pe_display_label') or 'PE'}={stock['pe']:.2f}")
                if isinstance(stock.get("pb"), (int, float)):
                    metrics.append(f"{stock.get('pb_display_label') or 'PB'}={stock['pb']:.2f}")
                if isinstance(stock.get("dividend_yield"), (int, float)):
                    metrics.append(f"股息率={stock['dividend_yield']:.2f}%")
                if isinstance(stock.get("roe"), (int, float)):
                    metrics.append(f"ROE={stock['roe']:.2f}%")

                header = f"{index}. {stock.get('code', '')} {stock.get('name', '')}"
                if stock.get("industry"):
                    header += f"（{stock['industry']}）"
                lines.append(header)
                if metrics:
                    lines.append(f"   - Key indicators:{'; '.join(metrics[:5])}")
                if stock.get("reason"):
                    lines.append(f"   - Reason:{stock['reason']}")

        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({"stocks": stocks}, ensure_ascii=False, indent=2))
        lines.append("```")
        return "\n".join(lines)

    async def _invoke_tool_function(self, tool_name: str, **kwargs) -> str:
        func = (self._tool_functions or {}).get(tool_name)
        if not func:
            raise ValueError(f"Tool does not exist:{tool_name}")

        result = func(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return str(result or "")

    async def _run_locked_result_execution(
        self,
        message: str,
        locked_plan: dict,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> tuple[str, List[str], list[dict[str, Any]]]:
        """The tool is executed directly according to the approved planning parameters, and the final structured result is generated by the server."""
        tools_used: List[str] = []

        screen_args = locked_plan["screen"]
        raw_conditions = json.loads(screen_args.get("conditions_json", "[]"))
        await self._emit_progress(
            progress_callback,
            "status",
            phase="result",
            message="Run batch filters directly against approved execution plans",
        )
        screen_items, total_candidates = await _execute_screening_query(
            raw_conditions,
            int(screen_args.get("limit", 50)),
            screen_args.get("order_by_field", "total_mv"),
            screen_args.get("order_direction", "desc"),
        )
        screen_output = _format_screening_output(
            raw_conditions,
            screen_items,
            total_candidates,
            screen_args.get("order_by_field", "total_mv"),
        )
        tools_used.append("screen_stocks_by_criteria")

        batch_output = ""
        candidate_codes = [
            str(item.get("code") or item.get("symbol", "")).strip()
            for item in screen_items
            if str(item.get("code") or item.get("symbol", "")).strip()
        ]
        batch_plan = locked_plan.get("batch")
        if batch_plan and candidate_codes:
            batch_args = {
                "stock_codes_json": json.dumps(candidate_codes, ensure_ascii=False),
                "years": batch_plan.get("years", 3),
                "threshold_cv": batch_plan.get("threshold_cv", 0.3),
            }
            batch_output = await self._invoke_tool_function("batch_check_profit_consistency", **batch_args)
            tools_used.append("batch_check_profit_consistency")

        stocks = self._build_structured_stocks(
            screen_items,
            raw_conditions,
            screen_args.get("order_by_field", "total_mv"),
            batch_output,
        )
        reply = self._build_locked_result_reply(total_candidates, stocks, batch_output)
        return reply, tools_used, stocks

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: str,
        **data,
    ) -> None:
        """Send smart filtering progress events for WebSocket streaming display."""
        if not progress_callback:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        try:
            await progress_callback(payload)
        except Exception as e:
            logger.debug("[Smart filtering] Progress push failed(ignore): %s", e)

    def _build_conversation_title(self, message: str) -> str:
        text = re.sub(r"\s+", " ", (message or "").strip())
        if not text:
            return "未命名筛选"
        return text[:30]

    def _format_dt(self, value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None

    async def _ensure_conversation_doc_identity(self, doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None

        messages = doc.get("messages") or []
        first_user_message = next(
            (item.get("content", "") for item in messages if item.get("role") == "user"),
            "",
        )
        updates: Dict[str, Any] = {}
        if not doc.get("conversation_id"):
            updates["conversation_id"] = uuid.uuid4().hex
        if not doc.get("title"):
            updates["title"] = self._build_conversation_title(first_user_message)

        if updates:
            await self._db.screening_conversations.update_one({"_id": doc["_id"]}, {"$set": updates})
            doc.update(updates)

        return doc

    async def _get_conversation_doc(self, user_id: str, conversation_id: Optional[str] = None) -> Optional[dict]:
        if conversation_id:
            doc = await self._db.screening_conversations.find_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return await self._ensure_conversation_doc_identity(doc)

        doc = await self._db.screening_conversations.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return await self._ensure_conversation_doc_identity(doc)

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Core method: Processing user s stock selection request (three-stage process)

        stage 1 — Requirement confirmation (confirmation): LLM analyzes the requirements and returns understanding + Improvement suggestions without calling tools
        stage 2 — Execution planning (planning): LLM explains which tools to call and what parameters to use, but does not actually execute it.
        stage 3 — Execute screening (result): LLM calls the tool and returns 5 stocks
        """
        # 1. Get historical conversations
        resolved_conversation_id, history = await self._get_context_messages(user_id, conversation_id)
        if not resolved_conversation_id:
            resolved_conversation_id = conversation_id or uuid.uuid4().hex

        # 2. LLM Intent classification
        intent = await self._classify_intent(message, history)
        logger.info(f"[智能筛选] 用户={user_id} 意图分类={intent.get('intent')} 置信度={intent.get('confidence'):.2f}")

        # 3. First check whether it is a single stock query
        if intent.get("intent") == "single_stock_query":
            direct_result = await self._maybe_handle_single_stock_query(
                message,
                progress_callback=progress_callback,
            )
            if direct_result is not None:
                await self._save_message(
                    user_id,
                    resolved_conversation_id,
                    message,
                    direct_result["reply"],
                    direct_result.get("tools_used", []),
                    direct_result.get("stocks", []),
                    direct_result.get("phase", "result"),
                    is_fallback=False,
                )
                direct_result["conversation_id"] = resolved_conversation_id
                return direct_result

        if not await self._ensure_client():
            return {
                "reply": "Smart filtering is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings.",
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False,
            }

        set_current_user_id(user_id)

        # 4. Determine which stage you should enter now
        phase = self._determine_phase(history, message, intent)
        logger.info(f"[智能筛选] 用户={user_id} 当前阶段={phase} 消息={message[:50]}")
        await self._emit_progress(
            progress_callback,
            "phase_determined",
            phase=phase,
            message=(
                "正在分析您的筛选需求" if phase == "confirmation"
                else "正在生成筛选执行计划" if phase == "planning"
                else "正在执行批量筛选与验证"
            ),
        )

        # 5. Build message list (including history)
        # planning At this stage, the list of actually available tools needs to be passed into the prompt word to prevent LLM from hallucinating tool names.
        tool_summary = self._build_tool_summary(self._result_openai_tools) if phase == "planning" else ""
        system_prompt = self._get_system_prompt(phase, tool_summary, intent)
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        phase_history = self._select_phase_history(history, phase, message, intent)
        locked_plan = (
            self._extract_locked_execution_plan(phase_history)
            if phase == "result" and intent.get("intent") == "approval"
            else None
        )
        for h in phase_history:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        tools_used: List[str] = []
        structured_stocks: list = []

        async def _do_chat():
            nonlocal tools_used, structured_stocks
            if phase == "result":
                await self._emit_progress(
                    progress_callback,
                    "status",
                    phase=phase,
                    message="It has entered the execution stage and started to call the screening and stock watch list tools.",
                )
                if locked_plan:
                    logger.info("[Smart filtering] Directly execute the result phase using the approved plan")
                    content, locked_tools_used, locked_stocks = await self._run_locked_result_execution(
                        message,
                        locked_plan,
                        progress_callback=progress_callback,
                    )
                    tools_used.extend(locked_tools_used)
                    structured_stocks = locked_stocks
                    return content
                # Stage 3: Actual call to tool to perform filtering
                resp = await self._llm_client.achat(
                    messages,
                    tools=self._result_openai_tools,
                    auto_execute_tools=True,
                    max_tool_rounds=SCREENING_MAX_TOOL_ROUNDS,
                    tools_used=tools_used,
                    progress_callback=progress_callback,
                    log_payloads=True,
                    payload_log_label=f"intelligent_screening:{phase}",
                )
            else:
                await self._emit_progress(
                    progress_callback,
                    "status",
                    phase=phase,
                    message="正在生成阶段性回复",
                )
                # Phase 1 (confirmation) and phase 2 (planning): neither tool is called
                resp = await self._llm_client.achat(
                    messages,
                    tools=None,
                    log_payloads=True,
                    payload_log_label=f"intelligent_screening:{phase}",
                )
            return resp.content

        try:
            started_at = datetime.now(timezone.utc)
            content = await asyncio.wait_for(
                _do_chat(),
                timeout=SCREENING_RESULT_TIMEOUT_SECONDS if phase == "result" else ASSISTANT_TIMEOUT_SECONDS,
            )
            reply = content or "Sorry, the answer cannot be generated at the moment, please try again later."
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(
                f"[Smart filtering] Complete phase={phase} elapsed={elapsed:.2f}s tools_used={len(tools_used)}"
            )
            await self._emit_progress(
                progress_callback,
                "status",
                phase=phase,
                message=f"阶段处理完成，用时 {elapsed:.2f} 秒",
                tools_used=tools_used,
            )
        except asyncio.TimeoutError:
            timeout_seconds = (
                SCREENING_RESULT_TIMEOUT_SECONDS if phase == "result" else ASSISTANT_TIMEOUT_SECONDS
            )
            logger.warning(f"[智能筛选] 请求超时（{timeout_seconds}s，phase={phase}）")
            await self._emit_progress(
                progress_callback,
                "timeout",
                phase=phase,
                message=f"处理超时（{timeout_seconds} 秒）",
            )

            reply = self._build_timeout_reply(timeout_seconds)
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, [], "result")
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": [],
                "phase": "result",
                "conversation_id": resolved_conversation_id,
            }
        except Exception as e:
            logger.exception("[智能筛选] 对话失败")
            await self._emit_progress(
                progress_callback,
                "error",
                phase=phase,
                message=f"Processing failed:{str(e)}",
            )
            reply = f"An error occurred while processing your request:{str(e)}. Please try again later."
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, [], "result")
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": [],
                "phase": "result",
                "conversation_id": resolved_conversation_id,
            }

        # Extract stocks (result stage only)
        stocks = structured_stocks if phase == "result" and structured_stocks else self._extract_stocks(reply) if phase == "result" else []

        # Clean up JSON code block in reply (stock data has been returned via stocks field)
        if phase == "result":
            reply = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = re.sub(r'```\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = reply.strip()

        if phase == "result" and not stocks and "screen_stocks_by_criteria" in tools_used:
            reply = self._build_no_match_reply(message)
            stocks = []
            await self._emit_progress(
                progress_callback,
                "no_match",
                phase="result",
                message="No stocks matching the original filter criteria were found.",
                stocks=[],
            )
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, stocks, phase)
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": stocks,
                "phase": phase,
                "conversation_id": resolved_conversation_id,
                "is_fallback": False,
            }

        await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, stocks, phase)
        return {
            "reply": reply,
            "tools_used": tools_used,
            "stocks": stocks,
            "phase": phase,
            "conversation_id": resolved_conversation_id,
            "is_fallback": False,
        }

    def _determine_phase(self, history: list, message: str, intent: Dict[str, Any] = None) -> str:
        """
        Determine which stage the current message should enter based on LLM intent classification

        Return 'confirmation' → Phase 1: LLM analyzes requirements without calling tools
        Return 'planning'     → Phase 2: LLM interprets the execution plan without calling tools
        Return 'result'       → Stage 3: LLM calls the tool and returns the stock list
        """
        # no history → new needs → Confirmation phase
        if not history:
            return "confirmation"

        # Find the most recent assistant message
        last_assistant = self._find_last_assistant(history)

        if not last_assistant:
            return "confirmation"

        last_phase = last_assistant.get("phase", "")
        intent_type = intent.get("intent") if intent else None

        if last_phase == "confirmation":
            # The user responded to the confirmation message → Entering the planning stage
            return "planning"

        if last_phase == "planning":
            # User responded to planning message
            if intent_type == "adjustment":
                # Users need to adjust their needs → Go back to the confirmation stage and re-understand
                return "confirmation"
            # Approval of plans or other → Entering the execution phase
            return "result"

        # last_phase == "result"
        if intent_type == "new_request":
            # Brand new stock selection needs → Reconfirm
            return "confirmation"

        # adjustment/approval/follow_up/single_stock_query → All are left in the result stage for processing.
        return "result"

    async def _get_context_messages(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[str, list]:
        """Get the latest N conversation history, which is used to pass to LLM as context"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc or not doc.get("messages"):
            return conversation_id or "", []
        messages = doc["messages"]
        return doc.get("conversation_id", conversation_id or ""), messages[-MAX_CONTEXT_MESSAGES:]

    def _build_tool_summary(self, tools: Optional[list] = None) -> str:
        """Convert the currently registered tool list into text descriptions for system prompts in the planning stage"""
        target_tools = tools if tools is not None else self._openai_tools
        if not target_tools:
            return "（暂无可用工具）"
        lines = []
        for t in target_tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "无参数"
            lines.append(f"- `{name}`: {desc}\n  Parameters:{param_names}")
        return "\n".join(lines)

    def _get_system_prompt(self, phase: str, tool_summary: str = "", intent: Dict[str, Any] = None) -> str:
        """Construct system prompt words for stock picking experts (customized according to the stage)"""
        curr_date = _get_latest_trade_date()

        if phase == "confirmation":
            return f"""You are a professional A-share stock picking expert. Users have just put forward new stock selection requirements.

## Your task: Requirements analysis and confirmation

**Do not call any instruments and do not recommend stocks.** Please follow these steps to reply:

1. **Analyze and understand**: Refining the core conditions of user needs (industry, valuation, style, time dimension, etc.)
2. **show understanding**: Tell users in a clear list"I understand your need is..."
3. **Improvement suggestions**: Based on professional judgment, put forward 2-3 optional improvement suggestions (increase screening dimensions, adjust thresholds, supplementary considerations, etc.)
4. **Waiting for confirmation**: Explicitly ask the user whether"Filter by original requirements"Still"Filter after taking suggestions into consideration"

Additional rules:
- If the user uses low valuation  low PE  low PB This type of vague valuation description, but without a clear caliber, must explicitly point out this ambiguity during the confirmation stage.
- PE Relevant calibers should be distinguished `pe` (PE) and `pe_ttm` (PE(TTM)) 
- PB Relevant calibers should be distinguished `pb` (PB) and `pb_mrq` (PB(MRQ)) 
- When encountering such vague valuation requirements, you can first give a default recommended caliber, but the caliber must be clearly stated and the user must be prompted to confirm whether to adopt this caliber.

Reply format:
```
## 📋 needs analysis

I understand your stock selection needs are as follows:
- **Industry scope**: xxx
- **core conditions**: xxx
- **filter style**: xxx
- **Caliber to be confirmed**: If you mentioned Low PE/low PB/low valuation , I will further confirm using `pe` / `pe_ttm`, `pb` / `pb_mrq`

## 💡 Improvement suggestions

Based on professional analysis, I suggest you consider:
1. xxx (reason)
2. xxx (reason)
3. If low valuation It is a core requirement and it is recommended to adopt it explicitly. `pe_ttm` (PE(TTM)) Still `pe` (PE) , and adopt `pb_mrq` (PB(MRQ)) Still `pb` (PB) 

## ⏳ Please confirm

Please select:
- **Filter by original requirements** — Execute directly according to your conditions
- **Filter after taking suggestions** — Add the above improvement conditions before executing
```

Current date:{curr_date}
It only analyzes needs, does not recommend stocks, and does not use tools.
"""

        if phase == "planning":
            screening_fields_markdown = build_screening_fields_markdown(public_only=True)
            return f"""You are a professional A-share stock picking expert. The user has confirmed the stock selection needs, please formulate a detailed execution plan.

## List of available tools (strictly limited to the following tools, no other tool names may be used)

{tool_summary}

## `screen_stocks_by_criteria` Supported filter fields

{screening_fields_markdown}

Supported operators:> < >= <= == != between in not_in contains

**Note**: Fields such as audit_opinion_type (audit opinion type) and margin_of_safety_score (custom safety margin score) are not supported.
If user needs involve these conditions, please state in the plan that existing fields will be approximately replaced, or be honest about this restriction.

## Recommended two-step workflow

**The first step (wide-diameter batch screening)**: call `screen_stocks_by_criteria`, settings limit=50, According to hard indicators (PE(TTM)/PE, PB(MRQ)/PB, Market value, gearing ratio, is_st, etc.) to filter the candidate pool.
**Step Two (Profitability Stability Verification)**: Pass the list of candidate stock symbols to `batch_check_profit_consistency`, A query verifies the ROE stability in the past N years.**It is prohibited to repeatedly query financial data for each stock individually.**

## Field usage suggestions

- The valuation caliber must be written explicitly, not just in general terms. PE/PB : `pe` means PE,`pe_ttm` express PE(TTM), `pb` means PB,`pb_mrq` express PB(MRQ)
- If the user just says PE However, the caliber is not specified. Priority is given to specifying the fields you actually choose in the plan, for example Use `pe_ttm` (PE(TTM)) <= 15 or Use `pe` (PE) <= 15 
- If the user just says PB However, the caliber is not specified. Priority is given to specifying the fields you actually choose in the plan, for example Use `pb` (PB) <= 1.5 or Use `pb_mrq` (PB(MRQ)) <= 1.5 
- Prioritize using comparable ratio indicators for hard screening, such as PE(TTM)/PE, PB(MRQ)/PB, ROE, Gross profit margin, asset-liability ratio, current ratio, dividend rate
- `revenue_ttm`, `net_profit_ttm`, `n_cashflow_act` It is more suitable as a supplementary condition for quality and should not be used as the sole criterion alone.
- If the user emphasizes good cash flow  Solid profits  Financially sound , Prioritize `n_cashflow_act > 0`, `net_profit_ttm > 0`, `debt_to_assets`, `current_ratio`
- If the user emphasizes High dividends  Defensive , Prioritize `dividend_yield` and combine `debt_to_assets`, `n_cashflow_act`
- If the user emphasizes Latest financial report  Only view the latest financial reports , Passable `report_period` Add constraints

## Stock watch list linkage rules

- If the user explicitly requests After the screening is completed, add the stock to the watch list or Add last recommendation to stock watchlist , Can be called after the final recommendation is determined `add_stocks_to_favorites`
- If the user explicitly requests Tag/Tag/Tag  (Such as Tag Buffett ) , Priority call `add_stocks_to_favorites` and pass in `tags`
- If the user explicitly requests to be placed in a certain category/group (such as bank  To be analyzed ) , callable `add_stock_to_watchlist`, Use first when necessary `list_watchlist_groups` View existing categories
-  label and Group Not the same concept: tags written into stock watchlists `tags`, Group writing watchlist group
- Do not take the initiative to add stocks to your watch list if it is not explicitly proposed.

## Your Task: Execution Plan Description

**Do not call any instruments and do not recommend stocks.** Please describe in detail how you plan to perform this screening:

1. **Screening strategy**: Summarize the final filtering conditions and indicate which requirements can be supported by existing fields and which cannot be accurately filtered.
2. **Tool call plan**: **Only use tools from the list of available tools above**, List tool name and specific parameters
   - Step 1:`screen_stocks_by_criteria` JSON array of conditions (field/operator/value for each condition), limit suggestions 30-50
    - If a valuation field is used, the display caliber must be stated simultaneously in the text description, for example `pe_ttm` (PE(TTM))   `pb_mrq` (PB(MRQ))  
   - Step 2 (if you need to verify profitability stability):`batch_check_profit_consistency`, Pass in the candidate stock code list in step 1
3. **Data processing**: Explain how to select the final 5 stocks from the results returned by the tool (sort by, priority, etc.)
4. **Restrictions**: Honestly tell users which conditions cannot be accurately filtered (such as audit opinion types, customized safety margin scores)
5. **request approval**: Ask the user if they agree to the proposal

Reply format:
```
## 🔧 execution plan

### Filter criteria (final version)
- PE(TTM) < xxx (Use `pe_ttm` field)
- Market value > 50 billion (existing field support)
- Asset-liability ratio ≤ 60% (debt_to_assets field support)
- Non-ST shares (supported by is_st field)
- ROE stable in the past 3 years (batch_check_profit_consistency tool support)

### Tool call
**steps 1**: call `screen_stocks_by_criteria`
- conditions: [{{{{"field": "pe_ttm", "operator": "<", "value": 15}}}}, {{{{"field": "pb_mrq", "operator": "<=", "value": 1.5}}}}, {{{{"field": "total_mv", "operator": ">", "value": 50}}}}, {{{{"field": "is_st", "operator": "==", "value": false}}}}]
- limit: 50
- order_by_field: "pb_mrq"
- order_direction: "asc"

**steps 2**: call `batch_check_profit_consistency` (Verify the profitability stability of the candidate stocks in step 1 in batches)
- stock_codes_json: List of all stock symbols returned in step 1
- years: 3
- threshold_cv: 0.3

### Data processing
- Filter from step 2 results"Stable profits"stocks, press PB(MRQ) Take the first 5 in ascending order
- Make sure industries don t overlap

## ✅ Please confirm

The above is my execution plan, please choose:
- **Execute screening plan** — Execute this plan immediately
- **Re-describe requirements** — Re-adjust filters
```

Current date:{curr_date}
It only explains the plan, does not use tools, and does not recommend stocks.**It is strictly prohibited to use tool names other than those listed in the tool list.**
"""

        # phase == "result"
        intent_hint = ""
        if intent:
            intent_type = intent.get("intent")
            if intent_type == "adjustment":
                target = intent.get("adjustment_target")
                direction = intent.get("adjustment_direction")
                params = intent.get("explicit_parameters")
                intent_hint = f"""
## Current user intent analysis (important)

User wishes**Adjust filters**: 
- Adjust goals:{target or 'unknown indicator'}
- Adjust direction:{'relax conditions' if direction == 'loosen' else 'tighten conditions' if direction == 'tighten' else 'unknown'}
- Explicit parameters:{params or 'The user did not explicitly give a specific value, please infer based on the suggestions in the conversation history.'}

Please read the conversation history carefully to find the previous filtering conditions, then adjust them according to the user s intent and filter again.
Special note: If the assistant gives a specific adjustment suggestion form in the history (such as"relax ROE > 15% → ROE > 10%") , Please use that recommended value first.
"""
            elif intent_type == "approval":
                intent_hint = """
## Current user intent analysis (important)

The user has**Approve execution plan**, Please perform filtering immediately according to the previously planned parameters.
"""

        return f"""You are a professional A-share stock picking expert. The user has approved the execution plan, please execute the screening and recommend stocks immediately.
{intent_hint}
## Your task: Perform screening

1. **Call tool**: Called according to previously planned parameters `screen_stocks_by_criteria` Other tools to obtain data
2. **Featured recommendations**: Strictly recommended every time **5 only** The most eligible stocks
3. **Structured output**: Include the following JSON code block at the end of your answer

```json
{{{{
  "stocks": [
    {{{{
      "code": "600519",
      "name": "Kweichow Moutai",
      "industry": "Liquor",
      "price": 1680.00,
      "pe": 25.3,
    "pe_display_label": "PE",
      "pb": 8.5,
    "pb_display_label": "PB",
            "roe": 32.1,
            "roa": 18.6,
            "gross_margin": 51.2,
            "netprofit_margin": 24.8,
            "dividend_yield": 3.1,
            "debt_to_assets": 18.5,
            "assets_to_eqt": 1.42,
            "current_ratio": 4.2,
            "quick_ratio": 3.8,
            "cash_ratio": 1.9,
            "revenue_ttm": 123456789000,
            "net_profit_ttm": 45678900000,
            "n_cashflow_act": 39876500000,
            "report_period": "20250930",
      "pct_change": 2.1,
      "reason": "The leading white horse stock, with stable performance growth and valuation at the historical mid-range"
    }}}}
  ]
}}}}
```

## rules

- Current date:{curr_date}
- The default is to execute at most **Two rounds of data tool calls**: 
    - Round 1:`screen_stocks_by_criteria`
    - Round 2: Call only when absolutely necessary `batch_check_profit_consistency`
- If step 1 can directly select the final recommendation, then**skip**Step 2, directly output the final result
- Once enough data is available to generate final recommendations,**Stop calling tools immediately**
- Don t do it for Gather information Repeatedly change the threshold, repeat screening, or re-expand the scope; when the results under the current conditions are insufficient, the restrictions should be directly stated
- Recommend exactly 5 stocks each time, no more, no less
- Reasons for recommendations should be specific and combined with data.
- If ROE, dividend rate, asset-liability ratio, current ratio, and financial reporting period are already provided in the tool results, they should be put into the JSON field first to facilitate direct display on the front end.
- If ROA, gross profit margin, net profit margin, rolling revenue, rolling net profit, operating cash flow, equity multiplier, quick ratio, and cash ratio are already provided in the tool results, they can also be put into the JSON field to facilitate direct display on the front end.
- If the actual screening or display caliber is used `pe_ttm` / `pb_mrq`, The corresponding value must be written in `pe` / `pb` fields, and add them separately `pe_display_label` / `pb_display_label`, Strictly prohibited `PE(TTM)` written as `PE`, put `PB(MRQ)` written as `PB`
- If the user requests adjustments (e.g."Change industry""PE Lower") , Directly re-invoke the tool to adjust filtering
- If the user explicitly requests that the current recommendation result be added to the stock watch list, the user can call `add_stocks_to_favorites` One-time addition; if requested at the same time Tag/mark , pass tag `tags` Parameters are written together
- If the user explicitly requests to put the current recommendation results into a certain category/group, you can call `add_stock_to_watchlist`, Allows automatic creation of groups if they do not exist, e.g. bank  To be analyzed 
- If the user also requires Add to your choice + Tag + put into group , should be called first `add_stocks_to_favorites` Write tags and call again `add_stock_to_watchlist`
- Does not give specific buying/selling advice, only stock selection recommendations and analysis
- Only recommend A shares (Shanghai and Shenzhen Stock Exchanges)
"""

    def _extract_stocks(self, reply: str) -> list:
        """Extract structured stock list from LLM reply"""
        pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
        match = re.search(pattern, reply)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("stocks", [])
            except json.JSONDecodeError:
                pass
        return []

    async def _save_message(
        self, user_id: str, conversation_id: str, user_msg: str, assistant_reply: str,
        tools_used: List[str], stocks: list, phase: str, is_fallback: bool = False,
    ) -> None:
        """Persistent conversation messages arrive screening_conversations"""
        now = datetime.now(timezone.utc)
        user_entry = {"role": "user", "content": user_msg, "timestamp": now}
        assistant_entry = {
            "role": "assistant",
            "content": assistant_reply,
            "tools_used": tools_used,
            "stocks": stocks,
            "phase": phase,
            "is_fallback": is_fallback,
            "timestamp": now,
        }
        await self._db.screening_conversations.update_one(
            {"user_id": user_id, "conversation_id": conversation_id},
            {
                "$push": {
                    "messages": {
                        "$each": [user_entry, assistant_entry],
                        "$slice": -SCREENING_CONVERSATION_LIMIT,
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "title": self._build_conversation_title(user_msg),
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def run_direct_screening(
        self,
        user_id: str,
        criteria: str,
        max_stocks: int = 10,
    ) -> Dict[str, Any]:
        """
        Execute stock picking directly (single round, no confirmation/planning stage).
        For external calls such as MCP/API, without the need for multiple rounds of dialogue.

        Args:
            user_id: User ID (used for LLM quotas, etc.)
            criteria: Filter criteria (natural language) such as "PE Technology stocks less than 20"
            max_stocks: Maximum number of stocks returned, default 10

        Returns:
            {"reply": str, "stocks": list, "phase": "result"}
        """
        if not await self._ensure_client():
            return {
                "reply": "Smart filtering is temporarily unavailable, please check your LLM configuration.",
                "stocks": [],
                "phase": "result",
            }
        set_current_user_id(user_id)
        tools_used: List[str] = []

        async def _run_direct_flow() -> tuple[str, List[str], list]:
            planning_messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content=(
                        " [Direct execution mode] The user requires you to provide an executable stock selection plan within a single round."
                        "You are now only responsible for generating the tool execution plan in the planning phase. Do not call the tool or output the final stock recommendation."
                        f"The final limit on the number of stocks displayed is {max_stocks} Only.\n\n"
                        + self._get_system_prompt("planning", self._build_tool_summary(self._result_openai_tools))
                    ),
                ),
                Message(
                    role=MessageRole.USER,
                    content=f"Please directly generate a screening execution plan based on the following conditions without confirmation.\n\n Conditions:{criteria}",
                ),
            ]
            planning_response = await self._llm_client.achat(
                planning_messages,
                tools=None,
                log_payloads=True,
                payload_log_label="intelligent_screening:direct_planning",
            )
            planning_content = (planning_response.content if planning_response else None) or ""
            locked_plan = self._extract_locked_execution_plan([
                {"role": "assistant", "phase": "planning", "content": planning_content}
            ])
            if not locked_plan:
                raise ValueError("An executable filtering plan could not be parsed. Please add more specific filtering conditions and try again.")

            locked_plan["screen"]["limit"] = min(int(locked_plan["screen"].get("limit", max_stocks)), max_stocks)
            return await self._run_locked_result_execution(criteria, locked_plan)

        try:
            started_at = datetime.now(timezone.utc)
            reply, tools_used, stocks = await asyncio.wait_for(
                _run_direct_flow(),
                timeout=SCREENING_RESULT_TIMEOUT_SECONDS,
            )
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(f"[Smart filtering] run_direct_screening Complete elapsed={elapsed:.2f}s tools_used={len(tools_used)}")
        except asyncio.TimeoutError:
            reply = self._build_timeout_reply(SCREENING_RESULT_TIMEOUT_SECONDS)
            stocks = []
            tools_used = []
        except Exception as e:
            logger.exception("[Smart filtering] run_direct_screening failed")
            reply = f"An error occurred while processing the stock pick request:{str(e)}. Please try again later."
            stocks = []
        if not stocks and "screen_stocks_by_criteria" in tools_used:
            reply = self._build_no_match_reply(criteria)
            stocks = []

        return {"reply": reply, "stocks": stocks, "phase": "result", "is_fallback": False}

    async def get_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[Optional[str], list]:
        """获取完整对话历史"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc:
            return conversation_id, []
        return doc.get("conversation_id"), doc.get("messages", [])

    async def list_conversations(self, user_id: str) -> list:
        """获取会话列表摘要"""
        cursor = self._db.screening_conversations.find({"user_id": user_id}).sort([
            ("updated_at", -1),
            ("created_at", -1),
        ])
        docs = await cursor.to_list(length=100)

        items = []
        for raw_doc in docs:
            doc = await self._ensure_conversation_doc_identity(raw_doc)
            messages = doc.get("messages") or []
            preview = ""
            for item in reversed(messages):
                content = str(item.get("content") or "").strip()
                if content:
                    preview = re.sub(r"\s+", " ", content)[:80]
                    break

            items.append({
                "conversation_id": doc.get("conversation_id"),
                "title": doc.get("title") or self._build_conversation_title(preview),
                "preview": preview,
                "message_count": len(messages),
                "created_at": self._format_dt(doc.get("created_at")),
                "updated_at": self._format_dt(doc.get("updated_at")),
            })

        return items

    async def clear_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> None:
        """清空对话历史"""
        if conversation_id:
            await self._db.screening_conversations.delete_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return

        doc = await self._get_conversation_doc(user_id, None)
        if not doc:
            return
        await self._db.screening_conversations.delete_one({"_id": doc["_id"]})


# === intelligent_screening_v2.py ===
"""
Intelligent Screening Service V2 - Stock selection dialogue system based on intent understanding

Architecture design:
- Intent first: all decisions are based on LLM intent understanding, no hard-coded keywords
- State machine driver: clear dialogue state management
- End-to-end LLM coordination: LLM coordinates the entire process
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from motor.motor_asyncio import AsyncIOMotorDatabase
except ImportError:
    AsyncIOMotorClient = AsyncIOMotorDatabase = AsyncIOMotorCollection = object
from app.services.intelligent_assistant_service import (
    _get_assistant_llm_config,
    _get_latest_trade_date,
    ASSISTANT_TIMEOUT_SECONDS,
)
from core.tools import get_tool_registry, tool_metadata_list_to_openai
from core.tools.context import set_current_user_id
from core.tools.implementations.market.stock_screening_tool import _execute_screening_query, _format_screening_output
from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

# Independent budget for stock selection scenarios
SCREENING_MAX_TOOL_ROUNDS = 3
SCREENING_RESULT_TIMEOUT_SECONDS = 300
MAX_CONTEXT_MESSAGES = 20
SCREENING_CONVERSATION_LIMIT = 50


async def _recall_user_plans_memory(db, user_id: str, query: str) -> str:
    """Recall the user s trading plan discipline/preference (user_preference) memory and inject it into the stock selection prompt.

    Reference:docs/05-design/v3.0/unified-memory-layer-mem0.md §15.5 P0-2
    """
    if not user_id:
        return ""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        return await svc.recall_formatted(
            query=query or "选股偏好",
            user_id=user_id,
            scopes=["user_preference", "trade_pattern"],
            limit=8,
            max_chars=900,
        )
    except Exception as e:
        logger.debug(f"[Smart filtering V2][mem0] Memory recall failed (ignored): {e}")
        return ""


def _build_plan_directive(memory_block: str) -> str:
    """Construct the Multiple Transaction Plan Processing Rules guidance fragment; return an empty string when memory_block is empty."""
    if not memory_block:
        return ""
    return (
        f"\n{memory_block}\n"
        " [Multiple trading plan processing rules] If there are multiple User s current trading plan: xxx (v number) entries in [Historical Memory]"
        " (For example, medium and long-term value , short-term band and flexible reserve ), indicating that users maintain multiple sets of coexisting strategies at the same time. Please follow the following rules for stock selection this time:\n"
        "1) Priority is given to whether the user s current round of news is clearly specified (such as stock selection based on medium and long-term plans and short-term opportunities ). If so, the corresponding planning discipline will be used.\n"
        "2) If it is not explicitly specified, but the demand is strongly correlated ( long-term holding tends to be mid- to long-term; short-term chasing tends to be short-term), select based on correlation and explain according to your xxx plan in the reply.\n"
        "3) When the style is not obvious, first ask the user Which plan do you want to choose stocks according to? (Medium and long term/short term/flexible)] , before continuing; don t default to the first one or mix multiple schedule disciplines.\n"
        "4) It is strictly prohibited to mix the stop loss/position/stock selection criteria of different plans.\n"
    )


class DialogState(Enum):
    """对话状态枚举"""
    IDLE = "idle"
    CONFIRMING = "confirming"
    PLANNING = "planning"
    EXECUTING = "executing"
    DONE = "done"


class IntentType(Enum):
    """意图类型枚举"""
    NEW_REQUEST = "new_request"
    ADJUST = "adjust"
    APPROVE = "approve"
    FOLLOW_UP = "follow_up"
    SINGLE_STOCK = "single_stock"


@dataclass
class IntentResult:
    """意图分类结果"""
    intent: IntentType
    slots: Dict[str, Any]
    confidence: float
    clarification_needed: bool
    clarification_question: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "slots": self.slots,
            "confidence": self.confidence,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question
        }


@dataclass
class ScreeningChatResponse:
    """智能筛选对话响应"""
    reply: str
    tools_used: List[str]
    stocks: List[dict]
    phase: str
    conversation_id: Optional[str] = None
    is_fallback: bool = False


class IntentClassifier:
    """纯LLM驱动的意图分类器"""

    def __init__(self, llm_client: UnifiedLLMClient):
        self.llm_client = llm_client

    async def classify(self, message: str, history: List[dict]) -> IntentResult:
        """
        Classify user intent and fill slots

        Args:
            message: Latest user news
            history: Conversation history

        Returns:
            IntentResult: Intent classification results
        """
        history_summary = self._build_history_summary(history)

        system_prompt = """You are a professional conversational intent classifier. Please analyze the user s latest news and combine it with the conversation history to determine the user s intention.

Return strict JSON format with no additional text:
{
    "intent": "new_request" | "adjust" | "approve" | "follow_up" | "single_stock",
    "slots": {
        "target_metric": "roe" | "pe" | "pb" | "margin" | "debt" | "cashflow" | "other" | null,
        "adjust_direction": "loosen" | "tighten" | null,
        "target_value": "10%" | "20" | "30%" | null,
        "stock_code": "002582" | "600519" | null,
        "stock_name": "miss you so much" | "Kweichow Moutai" | null,
        "action": "add_favorite" | "analyze" | null
    },
    "confidence": 0.95,
    "clarification_needed": false,
    "clarification_question": null
}

Intent definition:
- new_request: Users put forward new stock selection needs
- adjust: The user wants to adjust the previous filtering conditions (relax, tighten, modify, etc.)
- approve: The user explicitly approves a plan ("execute", "According to this plan", "OK", "OK", "Confirm", "yes", "No problem"etc.)
- follow_up: The user asks based on the current results ("How about these ones?", "Add to your choice", "Analyze it"etc.)
- single_stock: User asks about a single stock

Slot filling instructions:
- target_metric: When intent=adjust, indicate which indicator the user wants to adjust
- adjust_direction: When intent=adjust when it is pointed out that it is relaxing(loosen)Still tighten(tighten)
- target_value: Specific parameter values explicitly mentioned by the user
- stock_code/stock_name: When intent=single_stock Or extract when follow_up involves a single stock
- action: What the user wants to do

Clarification mechanism:
- Only set when the intent is very vague and it is completely impossible to tell what the user wants to do.clarification_needed=true
- **User reply"Confirm""yes""OK""OK"While waiting for the words of approval,intent=approve, clarification_needed=false**
- Don t because"Missing key parameters"While triggering clarification, missing parameters can be added in subsequent stages.

Example:
- Users say"Help me choose low-valuation bank stocks" → intent=new_request
- Users say"Let s relax ROE first" → intent=adjust, target_metric=roe, adjust_direction=loosen
- Users say"Change PE to<20" → intent=adjust, target_metric=pe, adjust_direction=loosen, target_value="20"
- Users say"Execute screening plan" → intent=approve
- Users say"Add these to your choice" → intent=follow_up, action=add_favorite
- Users say"How about Kweichow Moutai?" → intent=single_stock, stock_name="Kweichow Moutai"
"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(
                role=MessageRole.USER,
                content=f"Conversation history:\n{history_summary}\n\n Latest user news:{message}"
            )
        ]

        try:
            resp = await self.llm_client.achat(
                messages,
                tools=None,
                log_payloads=True,
                payload_log_label="intent_classification_v2"
            )
            content = resp.content if resp else ""
            result = self._parse_intent_result(content)
            return result
        except Exception as e:
            logger.warning(f"[Intent classification] LLM call failed: {e}")
            # Return default intent on failure
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )

    def _build_history_summary(self, history: List[dict]) -> str:
        """构建历史摘要"""
        if not history:
            return "无对话历史"

        recent = history[-6:]  # The last 6 items are enough to understand the context
        summary = []
        for h in recent:
            role = "用户" if h["role"] == "user" else "助手"
            content = h["content"][:300] + "..." if len(h["content"]) > 300 else h["content"]
            phase = h.get("phase", "")
            phase_tag = f" [{phase}]" if phase else ""
            summary.append(f"{role}{phase_tag}: {content}")

        return "\n".join(summary)

    def _parse_intent_result(self, content: str) -> IntentResult:
        """解析LLM返回的意图结果"""
        # Extract JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )

        try:
            data = json.loads(json_match.group(0))
            intent_str = data.get("intent", "follow_up")
            intent = IntentType(intent_str) if intent_str in [t.value for t in IntentType] else IntentType.FOLLOW_UP

            return IntentResult(
                intent=intent,
                slots=data.get("slots", {}),
                confidence=float(data.get("confidence", 0.5)),
                clarification_needed=bool(data.get("clarification_needed", False)),
                clarification_question=data.get("clarification_question")
            )
        except Exception as e:
            logger.warning(f"[Intent classification] JSON Parsing failed: {e}")
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )


class StateMachine:
    """对话状态机"""

    def __init__(self):
        pass

    def determine_state(self, history: List[dict], intent: IntentResult) -> DialogState:
        """
        Determine current state based on history and intent

        Args:
            history: Conversation history
            intent: Intent classification results

        Returns:
            DialogState: The current state that should be entered
        """
        if not history:
            return DialogState.CONFIRMING

        last_assistant = self._find_last_assistant(history)
        if not last_assistant:
            return DialogState.CONFIRMING

        last_phase = last_assistant.get("phase", "")

        # Decide based on final stage and intent
        if last_phase == "confirmation":
            return DialogState.PLANNING

        if last_phase == "planning":
            if intent.intent == IntentType.ADJUST:
                return DialogState.CONFIRMING
            return DialogState.EXECUTING

        # last_phase == "result" (That is DONE)
        if intent.intent == IntentType.NEW_REQUEST:
            return DialogState.CONFIRMING

        # Other situations are handled in the EXECUTING/DONE state
        return DialogState.EXECUTING

    def _find_last_assistant(self, history: List[dict]) -> Optional[dict]:
        """Find the last assistant message"""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return msg
        return None


class IntelligentScreeningServiceV2:
    """
    Intelligent Screening Service V2 - Stock selection dialogue system based on intent understanding
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._openai_tools: Optional[list] = None
        self._result_openai_tools: Optional[list] = None
        self._tool_functions: Optional[dict] = None
        self._intent_classifier: Optional[IntentClassifier] = None
        self._state_machine = StateMachine()

    async def _ensure_client(self) -> bool:
        """Lazy loading of LLM clients and tools"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(self._db)
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
            self._intent_classifier = IntentClassifier(self._llm_client)
        except Exception as e:
            logger.error(f"[Smart filtering V2] Creating LLM client failed: {e}", exc_info=True)
            return False

        # Load stock picking related tools
        registry = get_tool_registry()
        all_metadata = registry.list_all()
        screening_metadata = [
            m for m in all_metadata
            if m.fc_enabled and (
                m.category in ["screening", "market", "fundamentals", "news", "china", "technical"]
                or m.id in ["add_stocks_to_favorites", "list_watchlist_groups", "add_stock_to_watchlist"]
            )
        ]
        self._openai_tools = tool_metadata_list_to_openai(screening_metadata)

        self._tool_functions = {}
        for tool in screening_metadata:
            func = registry.get_function(tool.id)
            if func:
                self._tool_functions[tool.id] = func

        # Only tools related to batch screening are retained in the results execution phase.
        self._result_openai_tools = self._filter_result_tools(self._openai_tools)
        if not self._result_openai_tools:
            self._result_openai_tools = self._openai_tools

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(f"[智能筛选V2] 已加载 {len(self._openai_tools)} 个选股工具")
        return True

    def _filter_result_tools(self, openai_tools: Optional[list]) -> list:
        """Available tools for filtering result stage"""
        if not openai_tools:
            return []

        allowlist = {"screen_stocks_by_criteria", "batch_check_profit_consistency",
                     "add_stocks_to_favorites", "list_watchlist_groups", "add_stock_to_watchlist"}
        filtered = []
        for t in openai_tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            name = fn.get("name")
            if name in allowlist:
                filtered.append(t)
        return filtered

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        核心对话入口
        """
        # 1. Get historical conversations
        resolved_conversation_id, history = await self._get_context_messages(user_id, conversation_id)
        if not resolved_conversation_id:
            resolved_conversation_id = conversation_id or uuid.uuid4().hex

        # 2. Make sure the LLM client is ready
        if not await self._ensure_client():
            return self._error_response("Smart filtering is temporarily unavailable, please check LLM configuration", resolved_conversation_id)

        set_current_user_id(user_id)

        # 3. Intent classification
        intent = await self._intent_classifier.classify(message, history)
        logger.info(f"[智能筛选V2] 用户={user_id} 意图={intent.intent.value} 置信度={intent.confidence:.2f}")

        # 4. State machine judgment (first judge the status, and then decide whether clarification is needed)
        state = self._state_machine.determine_state(history, intent)
        logger.info(f"[Smart filtering V2] Current status={state.value}")

        # 5. Clarification is only allowed during the confirmation phase; users should not follow up while they are responding to a confirmation question
        if state == DialogState.CONFIRMING and intent.clarification_needed and intent.clarification_question:
            response = {
                "reply": intent.clarification_question,
                "tools_used": [],
                "stocks": [],
                "phase": "confirming",
                "conversation_id": resolved_conversation_id,
                "is_fallback": False
            }
            await self._save_message(user_id, resolved_conversation_id, message, response["reply"], [], [], "confirming")
            return response

        # 6. Route to corresponding processor
        response: Optional[Dict[str, Any]] = None

        if state == DialogState.CONFIRMING:
            response = await self._handle_confirming(user_id, message, history, intent, resolved_conversation_id, progress_callback)
        elif state == DialogState.PLANNING:
            response = await self._handle_planning(user_id, message, history, intent, resolved_conversation_id, progress_callback)
        elif state in [DialogState.EXECUTING, DialogState.DONE]:
            response = await self._handle_executing(user_id, message, history, intent, resolved_conversation_id, progress_callback)

        if response is None:
            response = self._error_response("Processing failed, please try again later", resolved_conversation_id)

        return response

    async def _handle_confirming(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理确认阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="confirmation", message="正在分析您的筛选需求")

        # Recall the user's trading plan/preference memory and inject it into prompt (multi-plan scenario)
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)

        system_prompt = self._get_confirmation_prompt() + plan_directive
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        try:
            resp = await asyncio.wait_for(
                self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="screening_confirmation"),
                timeout=ASSISTANT_TIMEOUT_SECONDS
            )
            reply = resp.content if resp else "Sorry, processing failed"

            await self._save_message(user_id, conversation_id, message, reply, [], [], "confirmation")

            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "confirmation",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            return self._error_response("Processing timeout, please try again later", conversation_id)
        except Exception as e:
            logger.exception("[确认阶段] 处理失败")
            return self._error_response(f"处理失败: {str(e)}", conversation_id)

    async def _handle_planning(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理规划阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="planning", message="正在生成筛选执行计划")

        tool_summary = self._build_tool_summary(self._result_openai_tools)
        # Recall trading plan/preference memory
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)
        system_prompt = self._get_planning_prompt(tool_summary) + plan_directive

        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        try:
            resp = await asyncio.wait_for(
                self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="screening_planning"),
                timeout=ASSISTANT_TIMEOUT_SECONDS
            )
            reply = resp.content if resp else "Sorry, processing failed"

            await self._save_message(user_id, conversation_id, message, reply, [], [], "planning")

            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "planning",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            return self._error_response("Processing timeout, please try again later", conversation_id)
        except Exception as e:
            logger.exception("[规划阶段] 处理失败")
            return self._error_response(f"处理失败: {str(e)}", conversation_id)

    async def _handle_executing(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理执行阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="result", message="正在执行批量筛选与验证")

        # First check if there is an approved plan that can be executed directly
        locked_plan = self._extract_locked_execution_plan(history) if intent.intent == IntentType.APPROVE else None

        # Recall trading plan/preference memory
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)
        system_prompt = self._get_execution_prompt(intent, history) + plan_directive
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        tools_used: List[str] = []
        structured_stocks: List[dict] = []

        async def _do_execute():
            nonlocal tools_used, structured_stocks

            if locked_plan:
                logger.info("[Smart filtering V2] Execute directly using approved plan")
                reply, locked_tools, locked_stocks = await self._run_locked_result_execution(
                    message, locked_plan, progress_callback
                )
                tools_used.extend(locked_tools)
                structured_stocks = locked_stocks
                return reply

            # Ordinary execution process
            resp = await self._llm_client.achat(
                messages,
                tools=self._result_openai_tools,
                auto_execute_tools=True,
                max_tool_rounds=SCREENING_MAX_TOOL_ROUNDS,
                tools_used=tools_used,
                progress_callback=progress_callback,
                log_payloads=True,
                payload_log_label="screening_execution"
            )
            return resp.content if resp else ""

        try:
            started_at = datetime.now(timezone.utc)
            reply = await asyncio.wait_for(_do_execute(), timeout=SCREENING_RESULT_TIMEOUT_SECONDS)
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(f"[智能筛选V2] 执行完成 耗时={elapsed:.2f}s 工具={tools_used}")

            await self._emit_progress(progress_callback, "status", phase="result",
                                     message=f"阶段处理完成，用时 {elapsed:.2f} 秒", tools_used=tools_used)

            # Withdraw shares
            if not structured_stocks:
                structured_stocks = self._extract_stocks(reply)

            # Clean up JSON code block in reply (stock data has been returned via stocks field)
            reply = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = re.sub(r'```\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = reply.strip()

            # If no stock is found and the filter tool is used, a clear no-result message is returned.
            if not structured_stocks and "screen_stocks_by_criteria" in tools_used:
                reply = self._build_no_match_reply(message)
                structured_stocks = []

            await self._save_message(user_id, conversation_id, message, reply, tools_used, structured_stocks, "result")

            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": structured_stocks,
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            reply = self._build_timeout_reply(SCREENING_RESULT_TIMEOUT_SECONDS)
            await self._save_message(user_id, conversation_id, message, reply, [], [], "result")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except Exception as e:
            logger.exception("[执行阶段] 处理失败")
            reply = f"处理您的请求时发生错误: {str(e)}。请稍后重试。"
            await self._save_message(user_id, conversation_id, message, reply, [], [], "result")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }

    def _get_confirmation_prompt(self) -> str:
        """获取确认阶段提示词"""
        curr_date = _get_latest_trade_date()
        return f"""You are a professional A-share stock picking expert. Users have put forward stock selection or industry research needs.

## Your task: Requirements analysis and confirmation

**Do not call any instruments and do not recommend stocks.** Please follow these steps to reply:

1. **Analyze and understand**: Refining the core conditions of user needs (industry, valuation, style, time dimension, etc.)
2. **show understanding**: Tell users in a clear list"I understand your need is..."
3. **Improvement suggestions**: Based on professional judgment, make 2-3 optional suggestions for improvement.
4. **Waiting for confirmation**: Explicitly ask the user whether"Filter by original requirements"Still"Filter after taking suggestions into consideration"

## Important rules

- **Industry/sector issues**: Such as"What are the leaders in the pig industry?", should be understood as"Screen the leading companies in the industry sorted by market capitalization/revenue", Convert to filter criteria (industry=xxx + Descending order by market capitalization + Take the first N items),**Don t ask for specific stock names**
- **User reply"Confirm""OK""yes""OK"Wait**: Indicate approval of the current plan and do not ask further questions.
- If the user uses"low valuation"This type of vague description, but no clear caliber, please point out the ambiguity and suggest a default value
- PE Relevant caliber distinction PE / PE(TTM)
- PB Relevant caliber distinction PB / PB(MRQ)

Current date:{curr_date}
It only analyzes needs, does not recommend stocks, and does not use tools.
"""

    def _get_planning_prompt(self, tool_summary: str) -> str:
        """获取规划阶段提示词"""
        curr_date = _get_latest_trade_date()
        screening_fields = build_screening_fields_markdown(public_only=True)
        return f"""You are a professional A-share stock picking expert. The user has confirmed the stock selection needs, please formulate a detailed execution plan.

## List of available tools

{tool_summary}

## `screen_stocks_by_criteria` Supported filter fields

{screening_fields}

Supported operators:> < >= <= == != between in not_in contains

## Your Task: Execution Plan Description

**Do not call any instruments and do not recommend stocks.** Please describe in detail how you plan to perform this screening:

1. **Screening strategy**: Summarize the final filtering criteria used
2. **Tool call plan**: List the tool name and specific parameters (conditions in JSON format)
3. **Data processing**: Explain how to select the final 5 stocks from the results returned by the tool
4. **request approval**: Ask the user if they agree to the proposal

Please clearly include in your response format:
- `conditions`: [...]  (JSON array of filter conditions)
- `limit`: 50  (number of candidates)
- `order_by_field`: "total_mv"  (sort field)
- `order_direction`: "desc"  (Sorting direction)

Current date:{curr_date}
It only explains the plan, does not use tools, and does not recommend stocks.
"""

    def _get_execution_prompt(self, intent: IntentResult, history: List[dict]) -> str:
        """获取执行阶段提示词"""
        curr_date = _get_latest_trade_date()

        intent_hint = ""
        if intent.intent == IntentType.ADJUST:
            target = intent.slots.get("target_metric", "未知指标")
            direction = intent.slots.get("adjust_direction", "")
            params = intent.slots.get("target_value", "")
            intent_hint = f"""
## Current user intent analysis (important)

User wishes**Adjust filters**: 
- Adjust goals:{target}
- Adjust direction:{'relax conditions' if direction == 'loosen' else 'tighten conditions' if direction == 'tighten' else ''}
- Explicit parameters:{params or 'The user did not explicitly give a specific value, please infer based on the suggestions in the conversation history.'}

Please read the conversation history carefully to find the previous filtering conditions, then adjust them according to the user s intent and filter again.
Special note: If the assistant gives a specific adjustment suggestion form in the history (such as"relax ROE > 15% → ROE > 10%") , Please use that recommended value first.
"""
        elif intent.intent == IntentType.APPROVE:
            intent_hint = """
## Current user intent analysis (important)

The user has**Approve execution plan**, Please perform filtering immediately according to the previously planned parameters.
"""
        elif intent.intent == IntentType.FOLLOW_UP:
            action = intent.slots.get("action", "")
            if action == "add_favorite":
                intent_hint = """
## Current user intent analysis (important)

User wishes**Add filter results to watchlist**. Please:
1. call `add_stocks_to_favorites` Tool to add previously screened stocks to the user s watch list in batches
2. parameters `stocks_json` is a JSON array with the format of `[{"code":"002714","name":"Muyuan shares","market":"A shares"}]`
3. Passable `tags` Parameters label this batch of stocks (if the user specifies a group name, it can be used as a label)
4. Tell the user the results of the operation

**don t say"Unable to obtain group information"Or let the user operate manually, which must be completed by calling a tool.**
"""
            else:
                intent_hint = """
## Current user intent analysis (important)

User is in**Ask for current results**. Please use the appropriate tool to answer the user s question.
"""

        return f"""你是一位专业的 A 股选股专家。
{intent_hint}

## 你的任务

### 筛选任务
1. **调用工具**：按计划调用 `screen_stocks_by_criteria` 等工具获取数据
2. **精选推荐**：每次严格推荐 **5 只** 最符合条件的股票（如果筛选结果不足5只，就推荐实际找到的数量）
3. **结构化输出**：在回答最后包含以下 JSON 代码块

```json
{{
    "stocks": [
        {{
            "code": "002582",
            "name": "好想你",
            "industry": "食品",
            "price": 12.34,
            "pe": 2.78,
            "pe_display_label": "PE(TTM)",
            "pb": 1.05,
            "pb_display_label": "PB(MRQ)",
            "roe": 24.4,
            "dividend_yield": 8.11,
            "debt_to_assets": 32.0,
            "reason": "推荐理由..."
        }}
    ]
}}
```

### 关注列表操作
- 用户说"加入自选""加入关注"时，调用 `add_stocks_to_favorites` 批量添加到关注列表
- 参数 `stocks_json` 格式：`[{{"code":"002714","name":"牧原股份","market":"A股"}}]`
- 可通过 `tags` 参数给这批股票打标签
- **不要让用户手动操作，必须通过工具完成**

当前日期：{curr_date}
- 最多执行 {SCREENING_MAX_TOOL_ROUNDS} 轮工具调用
- 如果工具结果中没有足够数据，就直接说明，不要编造
- 不要给出具体的买入/卖出建议，只做选股推荐和分析
- 只推荐 A 股（沪深两市）
"""

    def _build_tool_summary(self, tools: Optional[list] = None) -> str:
        """构建工具摘要"""
        target_tools = tools if tools is not None else self._openai_tools
        if not target_tools:
            return "（暂无可用工具）"
        lines = []
        for t in target_tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "无参数"
            lines.append(f"- `{name}`: {desc}\n  参数: {param_names}")
        return "\n".join(lines)

    def _extract_locked_execution_plan(self, history: List[dict]) -> Optional[dict]:
        """Extract approved execution plans from history"""
        latest_planning = None
        for item in reversed(history):
            if item.get("role") == "assistant" and item.get("phase") == "planning":
                latest_planning = item
                break

        if not latest_planning:
            return None

        content = str(latest_planning.get("content", ""))
        conditions_match = re.search(r'`?conditions`?\s*[:：]\s*`(\[[\s\S]*?\])`', content)
        limit_match = re.search(r'`?limit`?\s*[:：]\s*(\d+)', content)
        order_by_match = re.search(r'`?order_by_field`?\s*[:：]\s*"([^"]+)"', content)
        order_direction_match = re.search(r'`?order_direction`?\s*[:：]\s*"([^"]+)"', content)

        if not conditions_match:
            return None

        try:
            raw_conditions = json.loads(conditions_match.group(1))
        except json.JSONDecodeError:
            return None

        if not isinstance(raw_conditions, list) or not raw_conditions:
            return None

        return {
            "planning_content": content,
            "screen": {
                "conditions_json": json.dumps(raw_conditions, ensure_ascii=False),
                "limit": int(limit_match.group(1)) if limit_match else 50,
                "order_by_field": order_by_match.group(1) if order_by_match else "total_mv",
                "order_direction": order_direction_match.group(1) if order_direction_match else "desc",
            }
        }

    async def _run_locked_result_execution(
        self,
        message: str,
        locked_plan: dict,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> tuple[str, List[str], List[dict]]:
        """按已批准计划直接执行"""
        tools_used: List[str] = []

        screen_args = locked_plan["screen"]
        raw_conditions = json.loads(screen_args.get("conditions_json", "[]"))

        await self._emit_progress(
            progress_callback, "status", phase="result", message="Run batch filters directly against approved execution plans"
        )

        screen_items, total_candidates = await _execute_screening_query(
            raw_conditions,
            int(screen_args.get("limit", 50)),
            screen_args.get("order_by_field", "total_mv"),
            screen_args.get("order_direction", "desc"),
        )
        tools_used.append("screen_stocks_by_criteria")

        stocks = self._build_structured_stocks(screen_items, raw_conditions, screen_args.get("order_by_field", "total_mv"), "")
        reply = self._build_locked_result_reply(total_candidates, stocks, "")

        return reply, tools_used, stocks

    def _build_structured_stocks(self, items: list, raw_conditions: list, order_by_field: str, batch_output: str) -> List[dict]:
        """构建结构化股票列表"""
        if not items:
            return []

        stocks: List[dict] = []
        for item in items[:5]:
            code = str(item.get("code") or item.get("symbol", "")).strip()
            if not code:
                continue

            pe_display_field, pe_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pe")
            pb_display_field, pb_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pb")

            stocks.append({
                "code": code,
                "name": str(item.get("name", "")),
                "industry": str(item.get("industry", "")),
                "price": item.get("close"),
                "pe": resolve_metric_value(item, pe_display_field, "pe"),
                "pe_display_label": pe_display_label,
                "pb": resolve_metric_value(item, pb_display_field, "pb"),
                "pb_display_label": pb_display_label,
                "roe": item.get("roe"),
                "roa": item.get("roa"),
                "gross_margin": item.get("gross_margin"),
                "netprofit_margin": item.get("netprofit_margin"),
                "dividend_yield": item.get("dividend_yield"),
                "debt_to_assets": item.get("debt_to_assets"),
                "assets_to_eqt": item.get("assets_to_eqt"),
                "current_ratio": item.get("current_ratio"),
                "quick_ratio": item.get("quick_ratio"),
                "cash_ratio": item.get("cash_ratio"),
                "revenue_ttm": item.get("revenue_ttm"),
                "netprofit_ttm": item.get("net_profit_ttm"),
                "n_cashflow_act": item.get("n_cashflow_act"),
                "report_period": item.get("report_period"),
                "pct_change": item.get("pct_change"),
                "reason": "符合筛选条件"
            })
        return stocks

    def _build_locked_result_reply(self, total_candidates: int, stocks: List[dict], batch_output: str) -> str:
        """构建结果回复"""
        lines = ["The approved screening plan has been implemented."]
        if total_candidates:
            lines.append(f"共筛出 {total_candidates} 只候选。")

        if not stocks:
            lines.append("No matching stocks found.")
        else:
            lines.append(f"以下是最符合条件的 {len(stocks)} 只候选：")
            for i, stock in enumerate(stocks, 1):
                metrics = []
                if stock.get("price"):
                    metrics.append(f"价格={stock['price']:.2f}")
                if stock.get("pe"):
                    metrics.append(f"{stock.get('pe_display_label', 'PE')}={stock['pe']:.2f}")
                if stock.get("pb"):
                    metrics.append(f"{stock.get('pb_display_label', 'PB')}={stock['pb']:.2f}")
                if stock.get("roe"):
                    metrics.append(f"ROE={stock['roe']:.2f}%")

                lines.append(f"{i}. {stock.get('code')} {stock.get('name')} ({stock.get('industry', 'unknown')})")
                if metrics:
                    lines.append(f"   - {'; '.join(metrics)}")

        return "\n".join(lines)

    def _extract_stocks(self, reply: str) -> List[dict]:
        """从LLM回复中提取股票"""
        pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
        match = re.search(pattern, reply)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("stocks", [])
            except json.JSONDecodeError:
                pass
        return []

    def _build_no_match_reply(self, message: str) -> str:
        """构建无匹配结果的回复"""
        return "No stocks matching the current filter criteria were found.\n\n There are currently no targets suitable for this screening requirement. If you still want to continue filtering, consider adjusting your criteria."

    def _build_timeout_reply(self, timeout_seconds: int) -> str:
        """构建超时回复"""
        return f"Sorry, processing your stock selection request has timed out (more than {timeout_seconds} seconds).\n\n Please narrow the filter scope, add more specific conditions, or try again later."

    def _error_response(self, message: str, conversation_id: str) -> Dict[str, Any]:
        """构建错误响应"""
        return {
            "reply": message,
            "tools_used": [],
            "stocks": [],
            "phase": "result",
            "conversation_id": conversation_id,
            "is_fallback": False
        }

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: str,
        **data
    ) -> None:
        """发送进度事件"""
        if not progress_callback:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data
        }
        try:
            await progress_callback(payload)
        except Exception as e:
            logger.debug("[Smart filtering V2] Progress push failed: %s", e)

    async def _save_message(
        self,
        user_id: str,
        conversation_id: str,
        user_msg: str,
        assistant_reply: str,
        tools_used: List[str],
        stocks: List[dict],
        phase: str,
        is_fallback: bool = False
    ) -> None:
        """保存消息到数据库"""
        now = datetime.now(timezone.utc)
        user_entry = {"role": "user", "content": user_msg, "timestamp": now}
        assistant_entry = {
            "role": "assistant",
            "content": assistant_reply,
            "tools_used": tools_used,
            "stocks": stocks,
            "phase": phase,
            "is_fallback": is_fallback,
            "timestamp": now,
        }

        await self._db.screening_conversations.update_one(
            {"user_id": user_id, "conversation_id": conversation_id},
            {
                "$push": {
                    "messages": {
                        "$each": [user_entry, assistant_entry],
                        "$slice": -SCREENING_CONVERSATION_LIMIT,
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "title": self._build_conversation_title(user_msg),
                    "created_at": now,
                },
            },
            upsert=True,
        )

    def _build_conversation_title(self, message: str) -> str:
        """构建会话标题"""
        text = re.sub(r"\s+", " ", (message or "").strip())
        if not text:
            return "未命名筛选"
        return text[:30]

    async def _get_context_messages(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[str, List[dict]]:
        """获取历史对话消息"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc or not doc.get("messages"):
            return conversation_id or "", []
        messages = doc["messages"]
        return doc.get("conversation_id", conversation_id or ""), messages[-MAX_CONTEXT_MESSAGES:]

    async def _get_conversation_doc(self, user_id: str, conversation_id: Optional[str] = None) -> Optional[dict]:
        """获取会话文档"""
        if conversation_id:
            doc = await self._db.screening_conversations.find_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return doc

        doc = await self._db.screening_conversations.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return doc

    async def get_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[Optional[str], List[dict]]:
        """获取完整对话历史"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc:
            return conversation_id, []
        return doc.get("conversation_id"), doc.get("messages", [])

    async def list_conversations(self, user_id: str) -> List[dict]:
        """获取会话列表"""
        cursor = self._db.screening_conversations.find({"user_id": user_id}).sort([
            ("updated_at", -1),
            ("created_at", -1),
        ])
        docs = await cursor.to_list(length=100)

        items = []
        for doc in docs:
            messages = doc.get("messages", [])
            preview = ""
            for item in reversed(messages):
                content = str(item.get("content", "")).strip()
                if content:
                    preview = re.sub(r"\s+", " ", content)[:80]
                    break

            items.append({
                "conversation_id": doc.get("conversation_id"),
                "title": doc.get("title") or self._build_conversation_title(preview),
                "preview": preview,
                "message_count": len(messages),
                "created_at": self._format_dt(doc.get("created_at")),
                "updated_at": self._format_dt(doc.get("updated_at")),
            })
        return items

    async def clear_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> None:
        """清空会话"""
        if conversation_id:
            await self._db.screening_conversations.delete_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return

        doc = await self._get_conversation_doc(user_id, None)
        if doc:
            await self._db.screening_conversations.delete_one({"_id": doc["_id"]})

    def _format_dt(self, value: Any) -> Optional[str]:
        """格式化日期"""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None

