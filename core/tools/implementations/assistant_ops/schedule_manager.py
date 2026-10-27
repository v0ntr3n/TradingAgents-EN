"""
Scheduled task management tools

Provides query, creation and enable/disable functions for scheduled analysis configuration.
User identity is obtained through core.tools.context.
"""

import logging
from typing import Annotated, Optional

from langchain_core.tools import tool

from core.tools.base import register_tool
from core.tools.context import require_current_user_id

logger = logging.getLogger(__name__)


@tool
@register_tool(
    tool_id="list_scheduled_configs",
    name="查看定时分析配置",
    description="Lists all scheduled analysis configurations created by the user, displaying the name, CRON time period, and enabled/disabled status. Note: Scheduled analysis configuration is different from stock watch list (stock watch list) and stock watch list grouping; the former determines automatic analysis tasks, and the latter is just a stock pool or organization method.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "config", "list", "query", "assistant_ops", "cron", "scheduled_task", "task_config", "automation_config", "schedule_query"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["查看定时配置", "定时任务列表", "计划任务查询", "自动分析配置查看"],
    when_to_use="This is used when the user wants to view the scheduled analysis configuration list that he has created and learn about the automatic analysis plans.",
    returns="Returns a scheduled analysis configuration list in text format, each containing configuration ID, name, enablement status, and CRON time period summary.",
)
async def list_scheduled_configs() -> str:
    """Lists a summary of all scheduled analysis configurations for the current user."""
    from app.core.database import get_mongo_db

    user_id = require_current_user_id()
    db = get_mongo_db()

    cursor = db.scheduled_analysis_configs.find({"user_id": user_id}).sort("created_at", -1)

    configs = []
    async for doc in cursor:
        config_id = str(doc["_id"])
        name = doc.get("name", "未命名")
        enabled = "✅ 启用" if doc.get("enabled") else "⏸️ 禁用"
        slots = doc.get("time_slots", [])
        slot_summary = ", ".join(
            f"{s.get('name', '?')}({s.get('cron_expression', '?')})"
            for s in slots[:3]
        )
        if len(slots) > 3:
            slot_summary += f" +{len(slots) - 3}个"
        configs.append(f"  [{config_id[:8]}] {name} | {enabled} | {slot_summary}")

    if not configs:
        return "📋 There is currently no scheduled analysis configuration. You can ask me to create one for you."
    return f"📋 共 {len(configs)} 个定时分析配置：\n" + "\n".join(configs)


@tool
@register_tool(
    tool_id="create_scheduled_analysis",
    name="创建定时分析",
    description="Create a scheduled automatic analysis plan: specify the name, CRON time expression, and stock watch list grouping to be analyzed, and the system will automatically trigger the analysis according to the plan. Note: Only the groups configured here will enter timing analysis.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "create", "config", "cron", "assistant_ops", "automation", "scheduled_task", "task_creation", "analysis_plan", "cron_expression"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["创建定时分析", "设置自动分析", "定时任务创建", "CRON计划配置"],
    when_to_use="Used when the user wants to create a new scheduled automatic analysis plan, specify CRON time and stock watch list grouping.",
    returns="Returns a text message containing the name of the new configuration, configuration ID, time period, analysis depth, and enabling status.",
)
async def create_scheduled_analysis(
    name: Annotated[str, "Configuration name, such as Daily Morning Analysis "],
    cron_expression: Annotated[str, "CRON Expressions such as 0 9 * * 1-5 Indicates 9 a.m. on weekdays"],
    group_ids: Annotated[str, "Stock watch list group ID list, comma separated"],
    slot_name: Annotated[str, "Time period name, such as Before the market opens "] = "默认时段",
    depth: Annotated[int, "Analysis depth 1-5, default 3"] = 3,
) -> str:
    """Create a new scheduled analysis configuration containing a time period."""
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    # Check for name duplication
    existing = await db.scheduled_analysis_configs.find_one({"user_id": user_id, "name": name})
    if existing:
        return f"❌ 已存在同名配置「{name}」，请使用其他名称。"

    gid_list = [g.strip() for g in group_ids.split(",") if g.strip()]
    if not gid_list:
        return "❌ Please provide at least one stock watchlist group ID. You can first use View Stock Watch List Groups to obtain the group list."

    config_doc = {
        "user_id": user_id,
        "name": name,
        "description": "",
        "enabled": True,
        "time_slots": [{
            "name": slot_name,
            "cron_expression": cron_expression,
            "enabled": True,
            "group_ids": gid_list,
            "analysis_depth": depth,
        }],
        "default_group_ids": gid_list,
        "default_analysis_depth": depth,
        "default_quick_analysis_model": "",
        "default_deep_analysis_model": "",
        "default_prompt_template_id": None,
        "notify_on_complete": True,
        "notify_on_error": True,
        "send_email": False,
        "created_at": now_tz(),
        "updated_at": now_tz(),
    }

    result = await db.scheduled_analysis_configs.insert_one(config_doc)
    config_id = str(result.inserted_id)

    # Register to scheduler
    try:
        from app.pro.routers.scheduled_analysis import _register_scheduled_tasks
        config_doc["id"] = config_id
        await _register_scheduled_tasks(config_doc)
    except Exception as e:
        logger.warning(f"Failed to register scheduled tasks (configuration has been saved): {e}")

    return (
        f"✅ 定时分析配置已创建\n"
        f"- Name: {name}\n"
        f"- Configuration ID: {config_id}\n"
        f"- time period: {slot_name} ({cron_expression}) \n"
        f"- Analysis depth: {depth}\n"
        f"- Status: Enabled\n"
        f"The configuration will automatically perform analysis on a schedule."
    )


@tool
@register_tool(
    tool_id="toggle_scheduled_config",
    name="启用或禁用定时分析",
    description="Enable or disable existing scheduled analysis configurations (without deleting the configuration itself). Return the operation result and register or cancel the scheduler task synchronously.",
    category="assistant_ops",
    is_online=True,
    auto_register=True,
    timeout_tier="light",
    data_source_handling="local_only",
    capability_tags=["schedule", "scheduled_analysis", "toggle", "enable", "disable", "config", "assistant_ops", "scheduled_task", "automation_control", "task_status", "schedule_management"],
    tool_role_hint="primary",
    output_shape="text",
    preferred_for=["启用定时分析", "禁用定时分析", "切换任务状态", "暂停自动分析"],
    when_to_use="Used when the user wants to enable or disable an existing scheduled analysis configuration, pause or resume the automatic analysis plan.",
    returns="Returns a text message indicating the result of the configured enable/disable operation.",
)
async def toggle_scheduled_config(
    config_id: Annotated[str, "定时分析配置ID"],
    enabled: Annotated[bool, "True=enable, False=Disable"],
) -> str:
    """Enable or disable specified scheduled analysis configurations, and register or cancel scheduler tasks."""
    from bson import ObjectId
    from app.core.database import get_mongo_db
    from app.utils.timezone import now_tz

    user_id = require_current_user_id()
    db = get_mongo_db()

    try:
        oid = ObjectId(config_id)
    except Exception:
        return "❌ 无效的配置ID"

    config = await db.scheduled_analysis_configs.find_one({"_id": oid, "user_id": user_id})
    if not config:
        return f"❌ 未找到配置: {config_id}"

    if config.get("enabled") == enabled:
        status = "启用" if enabled else "禁用"
        return f"ℹ️ 配置「{config.get('name', '')}」已经是{status}状态。"

    await db.scheduled_analysis_configs.update_one(
        {"_id": oid},
        {"$set": {"enabled": enabled, "updated_at": now_tz()}},
    )

    # Update scheduler
    try:
        from app.pro.routers.scheduled_analysis import _register_scheduled_tasks, _unregister_scheduled_tasks
        if enabled:
            config["id"] = str(config.pop("_id"))
            config["enabled"] = True
            await _register_scheduled_tasks(config)
        else:
            await _unregister_scheduled_tasks(config_id)
    except Exception as e:
        logger.warning(f"Scheduler update failed (database updated): {e}")

    action = "启用" if enabled else "禁用"
    return f"✅ 已{action}定时分析配置「{config.get('name', '')}」"
