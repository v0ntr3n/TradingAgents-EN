"""
mem0 Custom MongoDB vector storage (client-side cosine similarity)

Replace mem0 official mem0.vector_stores.mongodb.MongoDB (depends on Atlas $vectorSearch) . 
MongoDB Community Edition is used to store vectors, and numpy is used on the Python side to calculate cosine similarity.

Registration method: Before mem0 is initialized, the VectorStoreFactory.provider_to_class["mongodb"]
Pointer to the MongoDBClientCosine class of this module.

Document structure (consistent with the official mem0 MongoDB, ensuring that you can switch back to Atlas in the future):
{
    "_id": "uuid-string",
    "embedding": [0.1, 0.2, ...],
    "payload": {
        "data": "original text",
        "memory": "post-retrieval memory",
        "user_id": "...",
        "agent_id": "...",
        "scope": "...",
        ...Others metadata
    }
}
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel
from pymongo import MongoClient, UpdateOne

logger = logging.getLogger(__name__)


class OutputData(BaseModel):
    """A data model that is completely consistent with mem0 official OutputData"""
    id: Optional[str] = None
    score: Optional[float] = None
    payload: Optional[dict] = None


class MongoDBClientCosine:
    """
    mem0 VectorStoreBase Compatible MongoDB vector storage (client cosine).

    The constructor signature is consistent with the mem0 official MongoDB class, allowing for seamless replacement:
        MongoDBClientCosine(db_name, collection_name, embedding_model_dims, mongo_uri)
    """

    VECTOR_TYPE = "vector"
    SIMILARITY_METRIC = "cosine"

    def __init__(
        self,
        db_name: str,
        collection_name: str,
        embedding_model_dims: int,
        mongo_uri: str,
    ):
        self.collection_name = collection_name
        self.embedding_model_dims = embedding_model_dims
        self.db_name = db_name
        self.mongo_uri = mongo_uri

        self.client = MongoClient(mongo_uri)
        self.db = self.client[db_name]
        self.collection = self._get_or_create_collection()

    def _get_or_create_collection(self):
        """Get or create a collection (idempotent, does not rely on Atlas Search Index)"""
        database = self.client[self.db_name]
        collection_names = database.list_collection_names(authorizedCollections=True)
        if self.collection_name not in collection_names:
            logger.info(
                "[mem0-mongodb] Collection '%s' Does not exist, automatically created",
                self.collection_name,
            )
            collection = database[self.collection_name]
            # Insert and delete placeholder documents to create collection
            collection.insert_one({"_id": "placeholder", "placeholder": True})
            collection.delete_one({"_id": "placeholder"})
        else:
            collection = database[self.collection_name]

        # Create common field indexes (accelerate metadata filtering)
        try:
            collection.create_index("payload.user_id")
            collection.create_index("payload.agent_id")
            collection.create_index("payload.scope")
            collection.create_index("payload.run_id")
        except Exception as e:
            logger.debug("[mem0-mongodb] Create index skip: %s", e)

        return collection

    # ------------------------------------------------------------------
    # VectorStoreBase Interface implementation
    # ------------------------------------------------------------------

    def create_col(self, name=None, vector_size=None, distance=None):
        """Create collection (mem0 called, but we created it in __init__)"""
        # If name is different from current, switch collection
        if name and name != self.collection_name:
            self.collection_name = name
            self.collection = self._get_or_create_collection()
        return self.collection

    def insert(
        self,
        vectors: List[List[float]],
        payloads: Optional[List[Dict]] = None,
        ids: Optional[List[str]] = None,
    ) -> None:
        """Insert vector (upsert semantics)"""
        operations = []
        for vector, payload, _id in zip(
            vectors,
            payloads or [{}] * len(vectors),
            ids or [None] * len(vectors),
        ):
            doc_id = _id or str(uuid.uuid4())
            operations.append(
                UpdateOne(
                    {"_id": doc_id},
                    {
                        "$set": {
                            "embedding": vector,
                            "payload": payload or {},
                        }
                    },
                    upsert=True,
                )
            )

        if operations:
            try:
                self.collection.bulk_write(operations, ordered=False)
                logger.debug(
                    "[mem0-mongodb] Insert %d items (collection=%s)",
                    len(operations),
                    self.collection_name,
                )
            except Exception as e:
                logger.error("[mem0-mongodb] Insertion failed: %s", e)

    def search(
        self,
        query: str,
        vectors: List[float],
        top_k: int = 5,
        filters: Optional[Dict] = None,
    ) -> List[OutputData]:
        """Vector similarity search (client cosine)

        Return List[OutputData], score is the similarity (the larger the more similar, the range [0, 1]) . 
        """
        try:
            if not vectors:
                return []

            query_vector = np.array(vectors, dtype=np.float32)
            query_norm = np.linalg.norm(query_vector)
            if query_norm == 0:
                return []

            # Build MongoDB query filter (based on payload subdocument)
            mongo_filter = self._build_mongo_filter(filters)

            # Read all documents (including embedding)
            cursor = self.collection.find(
                mongo_filter,
                {"_id": 1, "embedding": 1, "payload": 1},
            )

            docs = list(cursor)
            if not docs:
                return []

            # Construct a vector matrix and calculate cosine similarity
            valid_docs = []
            vectors_list = []
            for doc in docs:
                emb = doc.get("embedding")
                if not emb or not isinstance(emb, list):
                    continue
                # Skip zero vectors (signature point, etc.)
                if all(v == 0.0 for v in emb):
                    continue
                vectors_list.append(emb)
                valid_docs.append(doc)

            if not valid_docs:
                return []

            matrix = np.array(vectors_list, dtype=np.float32)
            matrix_norms = np.linalg.norm(matrix, axis=1)

            # Filter zero norm rows
            valid_mask = matrix_norms > 0
            if not np.any(valid_mask):
                return []

            valid_matrix = matrix[valid_mask]
            valid_docs_filtered = [d for d, v in zip(valid_docs, valid_mask) if v]
            valid_norms = matrix_norms[valid_mask]

            similarities = np.dot(valid_matrix, query_vector) / (valid_norms * query_norm)

            # top-k
            top_k = min(top_k, len(similarities))
            top_indices = np.argsort(similarities)[::-1][:top_k]

            results = []
            for idx in top_indices:
                doc = valid_docs_filtered[idx]
                results.append(
                    OutputData(
                        id=str(doc["_id"]),
                        score=float(similarities[idx]),
                        payload=doc.get("payload"),
                    )
                )

            logger.debug(
                "[mem0-mongodb] Search completed query='%s...' found=%d",
                str(query)[:30],
                len(results),
            )
            return results

        except Exception as e:
            logger.error("[mem0-mongodb] Search failed query=%s: %s", query, e)
            return []

    def delete(self, vector_id: str) -> None:
        """Delete by ID"""
        try:
            result = self.collection.delete_one({"_id": vector_id})
            if result.deleted_count > 0:
                logger.debug("[mem0-mongodb] Delete successfully id=%s", vector_id)
            else:
                logger.warning("[mem0-mongodb] Not found to delete id=%s", vector_id)
        except Exception as e:
            logger.error("[mem0-mongodb] Delete failed: %s", e)

    def update(
        self,
        vector_id: str,
        vector: Optional[List[float]] = None,
        payload: Optional[Dict] = None,
    ) -> None:
        """Update vector sum payload"""
        update_fields = {}
        if vector is not None:
            update_fields["embedding"] = vector
        if payload is not None:
            update_fields["payload"] = payload

        if update_fields:
            try:
                result = self.collection.update_one(
                    {"_id": vector_id}, {"$set": update_fields}
                )
                if result.matched_count > 0:
                    logger.debug("[mem0-mongodb] Update successful id=%s", vector_id)
                else:
                    logger.warning("[mem0-mongodb] Not found to update id=%s", vector_id)
            except Exception as e:
                logger.error("[mem0-mongodb] Update failed: %s", e)

    def get(self, vector_id: str) -> Optional[OutputData]:
        """Search by ID"""
        try:
            doc = self.collection.find_one({"_id": vector_id})
            if doc:
                return OutputData(
                    id=str(doc["_id"]),
                    score=None,
                    payload=doc.get("payload"),
                )
            return None
        except Exception as e:
            logger.error("[mem0-mongodb] get failed: %s", e)
            return None

    def list_cols(self) -> List[str]:
        """list all collection"""
        try:
            return self.db.list_collection_names(authorizedCollections=True)
        except Exception as e:
            logger.error("[mem0-mongodb] list_cols failed: %s", e)
            return []

    def delete_col(self) -> None:
        """Delete collection"""
        try:
            self.collection.drop()
            logger.info("[mem0-mongodb] Delete collection '%s'", self.collection_name)
        except Exception as e:
            logger.error("[mem0-mongodb] delete_col failed: %s", e)

    def col_info(self) -> Dict[str, Any]:
        """Get collection information"""
        try:
            stats = self.db.command("collstats", self.collection_name)
            return {
                "name": self.collection_name,
                "count": stats.get("count", 0),
                "size": stats.get("size", 0),
            }
        except Exception as e:
            logger.error("[mem0-mongodb] col_info failed: %s", e)
            return {}

    def list(self, filters: Optional[Dict] = None, top_k: int = 100) -> List[OutputData]:
        """List vectors (optional filtering)"""
        try:
            mongo_filter = self._build_mongo_filter(filters)
            cursor = self.collection.find(mongo_filter).limit(top_k)
            results = [
                OutputData(id=str(doc["_id"]), score=None, payload=doc.get("payload"))
                for doc in cursor
            ]
            return [results]
        except Exception as e:
            logger.error("[mem0-mongodb] list failed: %s", e)
            return [[]]

    def reset(self) -> None:
        """Reset collection (delete and recreate)"""
        logger.warning("[mem0-mongodb] reset collection '%s'", self.collection_name)
        self.delete_col()
        self.collection = self._get_or_create_collection()

    def __del__(self):
        try:
            if hasattr(self, "client"):
                self.client.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # internal tools
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_filter_value(key: str, value: Any) -> None:
        """Prevent MongoDB injection"""
        if isinstance(value, dict):
            raise ValueError(
                f"Filter value for {key!r} must be a scalar, not a dict."
            )
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    raise ValueError(
                        f"Filter list for {key!r} contains a dict."
                    )

    def _build_mongo_filter(self, filters: Optional[Dict]) -> Dict[str, Any]:
        """Convert mem0-style filters into MongoDB queries.

        mem0 filters is a flat key-value dict, stored in the payload subdocument,
        Therefore, the filter conditions need to be prefixed with payload.
        """
        if not filters:
            return {}

        for key, value in filters.items():
            self._validate_filter_value(key, value)

        conditions = []
        for key, value in filters.items():
            conditions.append({f"payload.{key}": value})

        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}


def register_mem0_mongodb_provider():
    """Register the custom MongoDB client cosine vector store to mem0 s VectorStoreFactory.

    Called before mem0 is initialized (such as _ensure_init in service.py).
    Replace the official MongoDB provider (depends on Atlas $vectorSearch) is the client cosine version.
    """
    try:
        from mem0.utils.factory import VectorStoreFactory

        provider_path = "core.memory.mem0_mongodb_store.MongoDBClientCosine"
        VectorStoreFactory.provider_to_class["mongodb"] = provider_path
        logger.info(
            "✅ [mem0-mongodb] Custom MongoDB vector store registered provider (client cosine)"
        )
    except Exception as e:
        logger.error("❌ [mem0-mongodb] Failed to register provider: %s", e)
        raise
