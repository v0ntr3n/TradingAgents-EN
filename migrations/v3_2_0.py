"""
v3.2.0 migration - Vector storage migrated from Qdrant to MongoDB

Migrate content:
1. Create metadata indexes for vector-related MongoDB collections to speed up filtering during client-side cosine searches
2. Record the migration completion mark to facilitate troubleshooting

Background:
- v3.2.0 Switched vector storage backend from Qdrant to MongoDB (client cosine similarity)
- Vector data and business data are uniformly stored in MongoDB, reducing operation and maintenance components.
- The document structure of a vector collection is flat:{embedding, document, ...metadata}
- mem0 The document structure of the collection is nested:{embedding, payload: {...}}

All operations must be idempotent (safe to run multiple times).
"""

import logging

logger = logging.getLogger("migrations.v3_2_0")

VERSION = "3.2.0"
DESCRIPTION = "Vector Store Migration to MongoDB: Creating a Vector Collection Metadata Index"

# VectorStoreManager Collection of vectors used (flat document structure)
# Collection name pattern:memory_<agent_id>, user_manual_v3, knowledge_finance
_VECTOR_FLAT_COLLECTIONS = [
    "user_manual_v3",
    "knowledge_finance",
]

# mem0 Collection of vectors used (nested payload document structure)
# Collection name pattern:mem0_memories_<provider>_<model>_<dims>_<fingerprint>
_MEM0_COLLECTION_PREFIX = "mem0_memories"

# Common filter fields for flat document structures (cooperated with MongoDBVectorCollection)
_FLAT_INDEX_FIELDS = [
    ("title", 1),
    ("manual_type", 1),
    ("provider", 1),
    ("agent_id", 1),
    ("category", 1),
]

# mem0 Commonly used filtering fields for nested payload structures (cooperated with MongoDBClientCosine)
_MEM0_PAYLOAD_INDEX_FIELDS = [
    ("payload.user_id", 1),
    ("payload.agent_id", 1),
    ("payload.scope", 1),
    ("payload.run_id", 1),
]


async def _create_indexes_for_collection(db, collection_name: str, index_fields: list):
    """Create an index for the specified collection (idempotent, skip if it already exists)"""
    try:
        existing_indexes = await db[collection_name].list_indexes()
        existing_names = {idx["name"] async for idx in existing_indexes}
    except Exception:
        existing_names = set()

    created = 0
    for field, direction in index_fields:
        index_name = f"{field.replace('.', '_')}_idx"
        if index_name in existing_names:
            continue
        try:
            await db[collection_name].create_index(
                [(field, direction)], name=index_name, background=True
            )
            created += 1
        except Exception as e:
            logger.debug(
                "v3.2.0 migration: Create index %s.%s skipped: %s",
                collection_name, field, e,
            )
    return created


async def _migrate_vector_collection_indexes(db):
    """Create an index for a collection of vectors managed by VectorStoreManager"""
    total_created = 0

    # 1. A set of known fixed names
    for col_name in _VECTOR_FLAT_COLLECTIONS:
        # Check if the collection exists
        exists = col_name in await db.list_collection_names()
        if not exists:
            logger.debug(
                "v3.2.0 migration: Collection %s does not exist, index creation skipped", col_name
            )
            continue
        created = await _create_indexes_for_collection(db, col_name, _FLAT_INDEX_FIELDS)
        if created:
            logger.info(
                "v3.2.0 migration: Collection %s created %d indexes", col_name, created
            )
        total_created += created

    # 2. Dynamic collection:memory_<agent_id>
    all_collections = await db.list_collection_names()
    for col_name in all_collections:
        if col_name.startswith("memory_"):
            created = await _create_indexes_for_collection(db, col_name, _FLAT_INDEX_FIELDS)
            if created:
                logger.info(
                    "v3.2.0 migration: Collection %s created %d indexes", col_name, created
                )
            total_created += created

    return total_created


async def _migrate_mem0_collection_indexes(db):
    """Create an index into the collection of vectors managed by mem0"""
    total_created = 0
    all_collections = await db.list_collection_names()

    for col_name in all_collections:
        if not col_name.startswith(_MEM0_COLLECTION_PREFIX):
            continue
        created = await _create_indexes_for_collection(db, col_name, _MEM0_PAYLOAD_INDEX_FIELDS)
        if created:
            logger.info(
                "v3.2.0 migration: mem0 Collection %s created %d indexes", col_name, created
            )
        total_created += created

    return total_created


async def upgrade(db):
    """Performing a v3.2.0 migration: Indexing a collection of vectors"""
    logger.info("v3.2.0 migration: Start creating vector collection index (Qdrant → MongoDB migration)")

    vector_created = await _migrate_vector_collection_indexes(db)
    mem0_created = await _migrate_mem0_collection_indexes(db)

    logger.info(
        "v3.2.0 migration: Complete — VectorStoreManager Collection %d indexes, "
        "mem0 Collection %d indexes",
        vector_created, mem0_created,
    )
    logger.info(
        "v3.2.0 migration: Description — Vector data will be provided on startup by UserManualManager etc."
        "Manager automatically indexes into MongoDB, no manual import required"
    )


async def downgrade(db):
    """Rollback v3.2.0 migration: delete the index created this time (optional)"""
    logger.info("v3.2.0 migration: rollback — Keep index (harmless, skip deletion)")
    # The index does not affect functionality and is not deleted.
