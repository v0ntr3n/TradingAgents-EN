"""
v3.1.0 migration - Agent Field completion during workshop runtime

Migrate content:
1. agent_configs: complete output_field / workflow_stage / report_label / show_in_reports / node_name / execution_order / callable_surfaces
2. prompt_templates: will agent_type="custom_agent" The workshop template is migrated to agent_type="universal"

All operations must be idempotent (safe to run multiple times).
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger("migrations.v3_1_0")

VERSION = "3.1.0"
DESCRIPTION = "Agent Field completion during workshop runtime: agent_configs field completion + Prompt Template agent_type migration"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _migrate_agent_configs(db):
    """Complete missing runtime fields in agent_configs"""
    collection = db["agent_configs"]
    migrated = 0

    async for doc in collection.find({"metadata.source": "agent_workshop"}):
        updates = {}
        unset_fields = {}

        # Top-level field completion
        # 🔥 output_field Must be unique, otherwise it will be shared by multiple workshop Agents analysis_report
        # Will cause runtime state to overwrite each other + After the aggregator removes duplicates, only the first one remains
        if not doc.get("output_field"):
            agent_id = doc.get("agent_id", "")
            # Generate unique field name from agent_id: take the last segment + _report
            if agent_id:
                tail = agent_id.replace("_v1", "").replace("_v2", "").split("_")[-1]
                default_output_field = f"{tail}_report"
            else:
                default_output_field = "analysis_report"
            updates["output_field"] = default_output_field
        if not doc.get("workflow_stage"):
            updates["workflow_stage"] = "analyst"
        if not doc.get("report_label"):
            name = doc.get("name", doc.get("agent_name", "Agent"))
            updates["report_label"] = f"【{name}】"
        if "show_in_reports" not in doc:
            updates["show_in_reports"] = True
        if not doc.get("node_name"):
            updates["node_name"] = doc.get("name", doc.get("agent_name", doc.get("agent_id", "")))
        if "execution_order" not in doc:
            updates["execution_order"] = 50
        if not doc.get("callable_surfaces"):
            updates["callable_surfaces"] = ["assistant", "workflow", "agent_workshop"]

        # metadata Field completion
        meta = doc.get("metadata", {})
        meta_updates = {}
        if not meta.get("workflow_stage"):
            meta_updates["metadata.workflow_stage"] = updates.get("workflow_stage", "analyst")
        if not meta.get("output_field"):
            meta_updates["metadata.output_field"] = updates.get("output_field", "analysis_report")
        if not meta.get("report_label"):
            meta_updates["metadata.report_label"] = updates.get("report_label", "")
        if "show_in_reports" not in meta:
            meta_updates["metadata.show_in_reports"] = True
        if not meta.get("node_name"):
            meta_updates["metadata.node_name"] = updates.get("node_name", "")
        if "execution_order" not in meta:
            meta_updates["metadata.execution_order"] = 50
        if not meta.get("callable_surfaces"):
            meta_updates["metadata.callable_surfaces"] = ["assistant", "workflow", "agent_workshop"]

        all_updates = {**updates, **meta_updates}
        if all_updates:
            all_updates["updated_at"] = _now_iso()
            await collection.update_one(
                {"_id": doc["_id"]},
                {"$set": all_updates},
            )
            migrated += 1

    if migrated:
        logger.info("v3.1.0 migration: agent_configs Complete %d records", migrated)
    else:
        logger.info("v3.1.0 migration: agent_configs No need to complete")


async def _migrate_prompt_templates(db):
    """will agent_type="custom_agent" The workshop template is migrated to agent_type="universal"

    Also make sure agent_name is consistent with version_id (try inferring from remark if missing).
    """
    collection = db["prompt_templates"]
    migrated = 0

    # Find agent_type="custom_agent" template
    async for doc in collection.find({"agent_type": "custom_agent"}):
        updates = {
            "agent_type": "universal",
            "updated_at": _now_iso(),
        }
        # If workflow_id exists, clear it (UniversalAgent does not include workflow_id when querying)
        if doc.get("workflow_id"):
            updates["workflow_id"] = None
        if doc.get("node_id"):
            updates["node_id"] = None

        await collection.update_one(
            {"_id": doc["_id"]},
            {"$set": updates},
        )
        migrated += 1

    if migrated:
        logger.info("v3.1.0 migration: prompt_templates Migrate %d items custom_agent → universal", migrated)
    else:
        logger.info("v3.1.0 migration: prompt_templates No need to migrate")


async def upgrade(db):
    """Perform v3.1.0 migration"""
    logger.info("v3.1.0 migration: Start field completion when running Agent Workshop")
    await _migrate_agent_configs(db)
    await _migrate_prompt_templates(db)
    logger.info("v3.1.0 migration: Complete")


async def downgrade(db):
    """Rollback v3.1.0 migration (rollback agent_type of prompt_templates only)"""
    logger.info("v3.1.0 migration: Start rollback")
    collection = db["prompt_templates"]
    result = await collection.update_many(
        {"agent_type": "universal", "remark": {"$regex": "Agent workshop"}},
        {"$set": {"agent_type": "custom_agent", "updated_at": _now_iso()}},
    )
    logger.info("v3.1.0 migration: Rollback %d items prompt_templates", result.modified_count)
