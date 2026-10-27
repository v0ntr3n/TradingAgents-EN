"""
v2.0.1 migration

# === Change analysis (e73b8a8b..HEAD) ===
# Files that may need schema migration:
#   - app/models/portfolio.py
#   - migrations/v2_0_0.py, migrations/v2_0_1.py (migration infra)
#   - tradingagents/dataflows/cache/mongodb_cache_adapter.py
# Suggested actions:
#   1. If new collections: create indexes (ref migrations/v2_0_0.py)
#   2. If new fields: update_many with default values
#   3. If field rename: $rename
"""

import logging


logger = logging.getLogger("migrations.v2_0_1")

VERSION = "2.0.1"
DESCRIPTION = "Example migration - adding migration_history index and system version records"


async def upgrade(db):
    """
    v2.0.1 migration. All operations are idempotent.
    """

    # --- 1: migration_history index ---
    await db.migration_history.create_index(
        [("status", 1), ("applied_at", -1)]
    )

    # --- 2: real_positions - add original_avg_cost for dual-cost display ---
    # For existing docs: copy cost_price into original_avg_cost only when missing.
    result = await db.real_positions.update_many(
        {
            "original_avg_cost": {"$exists": False},
            "cost_price": {"$exists": True, "$ne": None},
        },
        [
            {
                "$set": {
                    "original_avg_cost": "$cost_price"
                }
            }
        ]
    )
    logger.info(
        "v2.0.1 migration: backfilled original_avg_cost for %s real_positions docs",
        result.modified_count,
    )

    # --- Example 3: Insert new configuration data (only if it does not exist) ---
    # existing = await db.system_configs.find_one({"key": "new_feature_flag"})
    # if not existing:
    #     await db.system_configs.insert_one({
    #         "key": "new_feature_flag",
    #         "value": False,
    #         "description": "New function switch",
    #         "created_at": datetime.now(timezone.utc),
    #     })

    # --- Example 4: Modify field names of existing documents ---
    # await db.some_collection.update_many(
    #     {"old_field_name": {"$exists": True}},
    #     {"$rename": {"old_field_name": "new_field_name"}}
    # )

    # --- Example 5: Delete fields no longer needed ---
    # await db.some_collection.update_many(
    #     {"deprecated_field": {"$exists": True}},
    #     {"$unset": {"deprecated_field": ""}}
    # )


async def downgrade(db):
    """Rollback operation (optional)"""
    # Rollback example 2:
    # await db.agent_configs.update_many({}, {"$unset": {"timeout": ""}})
    pass

