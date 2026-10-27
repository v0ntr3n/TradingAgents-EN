"""
Market-wide stock batch screening tool

Encapsulate EnhancedScreeningService / DatabaseScreeningService,
Let LLM filter A shares in batches by condition through function calling.
"""

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from app.services.screening_metric_display import resolve_metric_value, select_metric_display_spec
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

