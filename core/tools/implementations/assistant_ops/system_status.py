"""Use the Q&A bot tool: Query system status.

Provides the ability to query system mode (standard/JD Cloud), current default model, data source activation status, version number, etc.
Allows using Q&A Assistant to"see"The current real state of the system.
"""

import logging
import os
from typing import Annotated

from langchain_core.tools import tool

from core.tools.base import register_tool

logger = logging.getLogger(__name__)


def _resolve_version() -> str:
    """Read VERSION file"""
    try:
        # Tool file path: core/tools/implementations/assistant_ops/system_status.py
        # Project root directory: Go to Level 4
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))
        version_path = os.path.join(project_root, "VERSION")
        if os.path.exists(version_path):
            with open(version_path, encoding="utf-8") as f:
                return f.read().strip()
    except Exception as exc:
        logger.warning("[get_system_status] Failed to read VERSION file: %s", exc)
    return "未知"


def _is_jdyun_mode() -> bool:
    """判断是否为京东云模式"""
    return os.environ.get("JDYUN_MODE", "false").lower() == "true"


@tool
@register_tool(
    tool_id="get_system_status",
    name="获取系统状态",
    description="Query the current operating mode of the system (standard version/JD Cloud version), default large model, data source activation status and version number. When the user asks'what version is this''What model are you currently using?''What are the data sources?'Use it when you have questions.",
    category="assistant_ops",
    is_online=False,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["usage_helper", "system_status", "jdyun_mode", "default_model", "data_sources", "version"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["当前是什么版本", "京东云版还是标准版", "当前用什么大模型", "数据源有哪些"],
    when_to_use="Used when the user asks about system configuration, schema, version, current model or data source status.",
    returns="Returns a system status summary in text format, including the operating mode, default model, data source list, and version number.",
)
async def get_system_status() -> str:
    """Get the current running status of the system."""
    from app.core.database import get_mongo_db

    db = get_mongo_db()
    jdyun = _is_jdyun_mode()
    version = _resolve_version()

    # Current default model
    default_model = "未配置"
    default_provider = "未配置"
    try:
        # Read enabled models from the llm_configs collection
        cursor = db.llm_configs.find({"enabled": True}, {"model_name": 1, "provider": 1, "is_default": 1}).limit(10)
        docs = await cursor.to_list(length=10)
        if docs:
            # Take priority is_default
            default_doc = next((d for d in docs if d.get("is_default")), docs[0])
            default_model = default_doc.get("model_name", "未知")
            default_provider = default_doc.get("provider", "未知")
    except Exception as exc:
        logger.warning("[get_system_status] Querying default model failed: %s", exc)

    # Data source enable status
    data_sources_lines = []
    try:
        cursor = db.data_sources.find({}, {"name": 1, "type": 1, "enabled": 1}).limit(20)
        docs = await cursor.to_list(length=20)
        if docs:
            for ds in docs:
                name = ds.get("name") or ds.get("type") or "?"
                ds_type = ds.get("type") or "?"
                enabled = "启用" if ds.get("enabled") else "禁用"
                # JD Cloud version hides unsupported data sources
                if jdyun and ds_type.lower() not in {"tushare", "akshare"}:
                    continue
                data_sources_lines.append(f"  - {name}({ds_type}): {enabled}")
        else:
            data_sources_lines.append("  - (The data source is not configured in the database)")
    except Exception as exc:
        logger.warning("[get_system_status] Querying data source failed: %s", exc)
        data_sources_lines.append(f"  - 查询失败: {exc}")

    lines = [
        "🖥️ 系统状态",
        f"- 运行模式: {'京东云版' if jdyun else '标准版'}",
        f"- 版本号: v{version}",
        f"- 默认大模型: {default_model} (厂家: {default_provider})",
        "- 数据源:",
    ]
    lines.extend(data_sources_lines or ["  - 无"])

    if jdyun:
        lines.append("- JD Cloud Version Instructions: Fully functional and open, no license required; large models and data sources are configured uniformly by the platform")

    return "\n".join(lines)
