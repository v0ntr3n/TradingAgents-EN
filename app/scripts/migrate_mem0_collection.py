"""
mem0 Qdrant collection Migration script

Purpose:
- Read the point of the old mem0 collection payload
- Regenerate vector using current mem0 embedder
- Write the current versioned new collection

Typical scenario:
- Embedding After the dimension is switched from 1536 to 1024, the old collection cannot continue to be written.
- Historical memory needs to be retained, but old vectors cannot be directly reused.

Example:
    python app/scripts/migrate_mem0_collection.py --source mem0_memories
    python app/scripts/migrate_mem0_collection.py --source mem0_memories --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("mem0.collection_migration")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate old mem0 Qdrant collection to current collection")
    parser.add_argument("--source", required=True, help="Old collection name, e.g. mem0_memories")
    parser.add_argument("--target", default="", help="The name of the target collection. By default, the current mem0 configuration is used to parse the result.")
    parser.add_argument("--batch-size", type=int, default=50, help="The number of points to migrate in each batch, default 50")
    parser.add_argument("--limit", type=int, default=0, help="The maximum number of items to be migrated, 0 means no limit")
    parser.add_argument("--dry-run", action="store_true", help="Only statistics and preview, no writing is performed")
    parser.add_argument("--overwrite", action="store_true", help="Allow overwriting when the target collection already has a point with the same ID")
    return parser.parse_args()


def _load_mem0_runtime() -> Tuple[Dict[str, Any], Any, Any, Any]:
    from mem0.utils.factory import EmbedderFactory
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    from app.core.database import get_mongo_db_sync
    from core.memory.config import build_mem0_config

    config = build_mem0_config(get_mongo_db_sync())
    return config, EmbedderFactory, QdrantClient, (Distance, PointStruct, VectorParams)


def _build_qdrant_client(config: Dict[str, Any], qdrant_client_cls):
    vector_cfg = (config.get("vector_store") or {}).get("config") or {}
    if vector_cfg.get("url"):
        kwargs = {"url": vector_cfg["url"]}
        if vector_cfg.get("api_key"):
            kwargs["api_key"] = vector_cfg["api_key"]
        return qdrant_client_cls(**kwargs)
    if vector_cfg.get("host") and vector_cfg.get("port"):
        kwargs = {"host": vector_cfg["host"], "port": vector_cfg["port"]}
        if vector_cfg.get("api_key"):
            kwargs["api_key"] = vector_cfg["api_key"]
        return qdrant_client_cls(**kwargs)
    return qdrant_client_cls(path=vector_cfg.get("path"))


def _ensure_target_collection(client, target_collection: str, vector_size: int, distance_cls, vector_params_cls) -> None:
    collections = client.get_collections().collections
    if any(col.name == target_collection for col in collections):
        info = client.get_collection(target_collection)
        existing_size = info.config.params.vectors.size
        if int(existing_size) != int(vector_size):
            raise RuntimeError(
                f"target collection {target_collection} Dimensions do not match: Existing {existing_size}, Expectation {vector_size}"
            )
        return

    client.create_collection(
        collection_name=target_collection,
        vectors_config=vector_params_cls(size=vector_size, distance=distance_cls.COSINE, on_disk=True),
    )
    logger.info("Goal created collection: %s (vector_size=%s)", target_collection, vector_size)


def _iter_source_points(client, source_collection: str, batch_size: int) -> Iterable[Sequence[Any]]:
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=source_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not points:
            break
        yield points
        if offset is None:
            break


def _build_embedder(config: Dict[str, Any], embedder_factory):
    embedder = config.get("embedder") or {}
    vector_store = config.get("vector_store") or {}
    return embedder_factory.create(
        embedder.get("provider"),
        embedder.get("config") or {},
        vector_store.get("config") or {},
    )


def _chunk_points_for_upsert(
    points: Sequence[Any],
    embedder: Any,
    point_struct_cls,
    overwrite: bool,
    existing_ids: Optional[set],
) -> Tuple[List[Any], int, int]:
    migrated: List[Any] = []
    skipped_missing_payload = 0
    skipped_existing = 0

    for point in points:
        payload = dict(point.payload or {})
        memory_text = str(payload.get("data") or "").strip()
        if not memory_text:
            skipped_missing_payload += 1
            continue

        point_id = point.id
        if not overwrite and existing_ids is not None and str(point_id) in existing_ids:
            skipped_existing += 1
            continue

        vector = embedder.embed(memory_text, "add")
        migrated.append(point_struct_cls(id=point_id, vector=vector, payload=payload))

    return migrated, skipped_missing_payload, skipped_existing


def _load_existing_ids(client, target_collection: str) -> set:
    existing_ids: set = set()
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=target_collection,
            limit=256,
            offset=offset,
            with_payload=False,
            with_vectors=False,
        )
        if not points:
            break
        for point in points:
            existing_ids.add(str(point.id))
        if offset is None:
            break
    return existing_ids


def main() -> int:
    args = _parse_args()

    config, embedder_factory, qdrant_client_cls, qdrant_models = _load_mem0_runtime()
    distance_cls, point_struct_cls, vector_params_cls = qdrant_models

    vector_cfg = (config.get("vector_store") or {}).get("config") or {}
    embedder_cfg = (config.get("embedder") or {}).get("config") or {}
    target_collection = args.target or str(vector_cfg.get("collection_name") or "").strip()
    source_collection = str(args.source or "").strip()

    if not source_collection:
        raise RuntimeError("--source collection name must be provided")
    if not target_collection:
        raise RuntimeError("The current mem0 configuration does not resolve the target collection")
    if source_collection == target_collection:
        raise RuntimeError("source Same as target collection, refuses to execute")

    vector_size = int(embedder_cfg.get("embedding_dims") or 0)
    if vector_size <= 0:
        raise RuntimeError("The current mem0 embedder has not parsed out a valid embedding_dims")

    client = _build_qdrant_client(config, qdrant_client_cls)
    collections = {col.name for col in client.get_collections().collections}
    if source_collection not in collections:
        raise RuntimeError(f"Source collection does not exist: {source_collection}")

    logger.info("Migration starts: source=%s target=%s dry_run=%s", source_collection, target_collection, args.dry_run)
    logger.info("current embedder: provider=%s model=%s dims=%s", (config.get("embedder") or {}).get("provider"), embedder_cfg.get("model"), vector_size)

    if not args.dry_run:
        _ensure_target_collection(client, target_collection, vector_size, distance_cls, vector_params_cls)

    embedder = _build_embedder(config, embedder_factory)
    existing_ids = None if args.overwrite or args.dry_run else _load_existing_ids(client, target_collection)

    total_seen = 0
    total_migrated = 0
    total_skipped_missing_payload = 0
    total_skipped_existing = 0

    for batch in _iter_source_points(client, source_collection, max(1, args.batch_size)):
        if args.limit and total_seen >= args.limit:
            break

        remaining = args.limit - total_seen if args.limit else 0
        current_batch = list(batch[:remaining]) if remaining else list(batch)
        if not current_batch:
            break

        total_seen += len(current_batch)
        migrated_points, skipped_missing_payload, skipped_existing = _chunk_points_for_upsert(
            current_batch,
            embedder,
            point_struct_cls,
            args.overwrite,
            existing_ids,
        )
        total_skipped_missing_payload += skipped_missing_payload
        total_skipped_existing += skipped_existing

        if not args.dry_run and migrated_points:
            client.upsert(collection_name=target_collection, points=migrated_points)

        total_migrated += len(migrated_points)
        logger.info(
            "Batch completed: seen=%s migrated=%s skipped_missing_payload=%s skipped_existing=%s",
            total_seen,
            total_migrated,
            total_skipped_missing_payload,
            total_skipped_existing,
        )

    logger.info(
        "Migration ends: source=%s target=%s seen=%s migrated=%s skipped_missing_payload=%s skipped_existing=%s dry_run=%s",
        source_collection,
        target_collection,
        total_seen,
        total_migrated,
        total_skipped_missing_payload,
        total_skipped_existing,
        args.dry_run,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        raise