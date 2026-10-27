"""L4 Project long-term memory default seed."""

from __future__ import annotations

from typing import Any, Dict, List

from app.models.project_memory import DEFAULT_PROJECT_MEMORY_PROJECT_ID, ProjectMemoryCategory


PROJECT_MEMORY_DEFAULT_VERSION = "v1"


def get_default_project_memory_items() -> List[Dict[str, Any]]:
    seed_meta = {
        "source": "system_seed",
        "seed_name": "project_memory_defaults",
        "seed_version": PROJECT_MEMORY_DEFAULT_VERSION,
    }
    return [
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "global-no-trading-advice",
            "title": "禁止直接投资建议",
            "content": "All analysis only provides research and learning reference, and does not provide direct trading advice on buying, selling, holding, target price, position or specific time point.",
            "category": ProjectMemoryCategory.PROJECT_RULE.value,
            "priority": 10,
            "tags": ["compliance", "assistant", "global"],
            "metadata": dict(seed_meta),
        },
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "financial-domain-boundary",
            "title": "服务边界限定在金融领域",
            "content": "Only briefly reject non-financial topics, and lead back to financial scenarios such as stocks, funds, macro, industries, positions, review or trading plans.",
            "category": ProjectMemoryCategory.PROJECT_RULE.value,
            "priority": 20,
            "tags": ["assistant", "boundary"],
            "metadata": dict(seed_meta),
        },
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "confirm-side-effect-operations",
            "title": "复杂副作用操作先确认",
            "content": "To create scheduled analysis, delete or remove objects, complex multi-step tasks, and analysis requests with unclear intentions, you must first explain the plan or confirm parameters before executing.",
            "category": ProjectMemoryCategory.GOVERNANCE_CONSTRAINT.value,
            "priority": 30,
            "tags": ["governance", "assistant_ops"],
            "metadata": dict(seed_meta),
        },
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "realtime-data-first",
            "title": "实时数据问题必须先取数",
            "content": "For questions involving market conditions, index points, financial report figures, technical indicators, recent announcements or the latest developments, you must first call the tool to obtain the data, and you cannot use training memory to fill in the answers.",
            "category": ProjectMemoryCategory.GOVERNANCE_CONSTRAINT.value,
            "priority": 40,
            "tags": ["data", "realtime", "governance"],
            "metadata": dict(seed_meta),
        },
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "answer-structure-conclusion-first",
            "title": "回答结构先结论后展开",
            "content": "By default, conclusions are given first, and then evidence, risks and uncertainties are given; if the tool data is not of the current caliber, the date of the data must be clearly marked.",
            "category": ProjectMemoryCategory.ANALYSIS_OUTPUT_CONSTRAINT.value,
            "priority": 50,
            "tags": ["output", "assistant", "analysis"],
            "metadata": dict(seed_meta),
        },
        {
            "project_id": DEFAULT_PROJECT_MEMORY_PROJECT_ID,
            "memory_key": "stock-analysis-template",
            "title": "个股分析默认结构",
            "content": "By default, individual stock analysis is organized by conclusion, core drivers, key risks, and points to be verified; when there is a lack of real-time data, the information gap will be explained before continuing the analysis.",
            "category": ProjectMemoryCategory.RESEARCH_TEMPLATE.value,
            "priority": 60,
            "tags": ["template", "stock_analysis"],
            "metadata": dict(seed_meta),
        },
    ]