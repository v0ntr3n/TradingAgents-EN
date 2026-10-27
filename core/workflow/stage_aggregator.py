"""
Stage report aggregator

During workflow execution, Agent output at the same stage is automatically aggregated into a unified report package.
Allow downstream Agents to pass {analyst_reports}, {research_reports}, {risk_reports}
Aggregate variables such as these reference all upstream reports without the need to hardcode individual field names.

Aggregation source:
1. AgentRegistry metadata for code registration
2. Agent Updates posted by the workshop to MongoDB agent_configs Agent
"""

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def _normalize_content(content: Any) -> str:
    if not content:
        return ""
    if isinstance(content, dict):
        content = content.get("content", "")
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    return content if len(content) >= 5 else ""


def _append_report(
    reports: List[Tuple[int, str, str]],
    seen_fields: set,
    state: Dict[str, Any],
    output_field: str,
    label: str,
    order: int,
) -> None:
    if not output_field or output_field in seen_fields:
        return
    content = _normalize_content(state.get(output_field, ""))
    if not content:
        return
    reports.append((order, label or output_field, content))
    seen_fields.add(output_field)


def _append_registry_reports(reports: List[Tuple[int, str, str]], seen_fields: set, state: Dict[str, Any], stage: str) -> None:
    try:
        from core.agents.registry import get_registry
        registry = get_registry()
        all_metas = registry.list_all() if hasattr(registry, "list_all") else []
    except Exception as e:
        logger.debug(f"Unable to obtain AgentRegistry: {e}")
        return

    for meta in all_metas:
        try:
            if not meta or meta.workflow_stage != stage:
                continue
            _append_report(
                reports,
                seen_fields,
                state,
                meta.output_field,
                meta.report_label or meta.output_field,
                meta.execution_order,
            )
        except Exception as e:
            logger.debug(f"Aggregation registration Agent report failure: {e}")


def _append_workshop_agent_reports(reports: List[Tuple[int, str, str]], seen_fields: set, state: Dict[str, Any], stage: str) -> None:
    """Aggregate dynamic Agent reports published by Agent Workshop from agent_configs."""
    try:
        from pymongo import MongoClient
        from tradingagents.config.mongodb_utils import build_mongodb_connection_string, get_mongodb_database_name

        client = MongoClient(build_mongodb_connection_string(), serverSelectionTimeoutMS=2000)
        db = client[get_mongodb_database_name()]
        docs = list(db.agent_configs.find({
            "enabled": True,
            "metadata.source": "agent_workshop",
            "version_status": "active",
            "runtime_status": "active",
            "$or": [
                {"workflow_stage": stage},
                {"metadata.workflow_stage": stage},
            ],
        }))
        client.close()
    except Exception as e:
        logger.debug(f"Aggregation of Agent workshop reports failed: {e}")
        return

    for doc in docs:
        output_field = doc.get("output_field") or (doc.get("metadata") or {}).get("output_field")
        label = doc.get("report_label") or f"【{doc.get('name') or doc.get('agent_id') or output_field}】"
        order = int(doc.get("execution_order") or (doc.get("metadata") or {}).get("execution_order") or 50)
        _append_report(reports, seen_fields, state, output_field, label, order)


def aggregate_stage_reports(state: Dict[str, Any], stage: str) -> str:
    """
    Aggregate reports from all Agents in the specified stage.

    Args:
        state: Current workflow status
        stage: Stage name (analyst/research/risk/manager/trader)
    """
    reports: List[Tuple[int, str, str]] = []
    seen_fields = set()

    _append_registry_reports(reports, seen_fields, state, stage)
    _append_workshop_agent_reports(reports, seen_fields, state, stage)

    reports.sort(key=lambda x: x[0])
    if not reports:
        return ""

    return "\n\n---\n\n".join(f"### {label}\n\n{content}" for _, label, content in reports)


def inject_stage_reports(state: Dict[str, Any], variables: Dict[str, Any]) -> None:
    """
    Inject stage aggregation reports into the template variable dictionary. Automatically generated:
    - analyst_reports
    - research_reports
    - risk_reports
    """
    stage_mapping = {
        "analyst_reports": "analyst",
        "research_reports": "research",
        "risk_reports": "risk",
    }

    for var_name, stage in stage_mapping.items():
        if var_name not in variables:
            aggregated = aggregate_stage_reports(state, stage)
            if aggregated:
                variables[var_name] = aggregated
