"""
v2.0.0 baseline migration

This is the first migration script, which records the current baseline state of the database.
This migration does not make any actual changes to the existing production database.
For freshly installed databases, this migration ensures that the core indexes are present.

This migration is idempotent and can be safely performed repeatedly.
"""

import logging

VERSION = "2.0.0"
DESCRIPTION = "Baseline Migration - Record v2.0.0 database status, ensure core indexing"

logger = logging.getLogger("migrations")


async def _safe_create_index(collection, keys, **kwargs):
    """Create an index safely - no error will be reported if it already exists (even if the options are different)"""
    try:
        await collection.create_index(keys, **kwargs)
    except Exception as e:
        err_code = getattr(e, 'code', None) if hasattr(e, 'code') else None
        # code 85 = IndexOptionsConflict (Index already exists but options are different)
        # code 86 = IndexKeySpecsConflict
        if err_code in (85, 86):
            name = kwargs.get('name', str(keys))
            logger.info(f"  ⏭️ Index already exists(Options are different), skip: {collection.name}.{name}")
        else:
            raise


async def upgrade(db):
    """Establish a baseline - make sure the core collection index exists"""

    # === User related index ===
    await _safe_create_index(db.users, "username", unique=True, sparse=True)

    # === Analysis task index ===
    await _safe_create_index(db.unified_analysis_tasks, [("created_at", -1)])
    await _safe_create_index(db.unified_analysis_tasks, "status")
    await _safe_create_index(db.unified_analysis_tasks, "user_id")

    # === Workflow configuration index ===
    await _safe_create_index(db.workflow_definitions, "workflow_id", unique=True, sparse=True)
    await _safe_create_index(db.agent_configs, "agent_id", unique=True, sparse=True)
    await _safe_create_index(db.tool_configs, "tool_id", unique=True, sparse=True)

    # === System configuration index ===
    await _safe_create_index(db.system_configs, "key", unique=True, sparse=True)
    await _safe_create_index(db.llm_providers, "provider_id", unique=True, sparse=True)

    # === Prompt word template index ===
    await _safe_create_index(db.prompt_templates, "template_id", unique=True, sparse=True)

    # === Migration history index ===
    await _safe_create_index(db.migration_history, "version", unique=True)
    await _safe_create_index(db.migration_history, [("applied_at", -1)])


async def downgrade(db):
    """Baseline migration does not support rollback"""
    raise NotImplementedError("Baseline migration does not support rollback")

