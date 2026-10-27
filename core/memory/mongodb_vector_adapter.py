"""
MongoDB Vector database adapter (client cosine similarity)

Features:
- Vector data is stored in MongoDB (unified with business data)
- Similarity calculation is completed on the Python side (numpy cosine) and does not rely on MongoDB $vectorSearch
- No file lock conflicts, support concurrent access by multiple processes
- It is completely consistent with the QdrantAdapter interface and the caller does not need to modify it.
- Suitable for small and medium-sized vector collections (< 10K strips), it is recommended to use Qdrant server mode for large amounts of data
"""

import logging
import os
import time
from typing import List, Dict, Any, Optional

import numpy as np
from pymongo import UpdateOne

logger = logging.getLogger(__name__)


def _translate_where_to_mongo(where: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Convert ChromaDB-style where conditions into MongoDB query filters.

    Supported formats:
    - {"key": "value"} → {"key": "value"}
    - {"$and": [{"k1": "v1"}, {"k2": "v2"}]} → {"$and": [{"k1": "v1"}, {"k2": "v2"}]}
    - {"key": {"$ne": "value"}} → {"key": {"$ne": "value"}} (direct)
    """
    if not where:
        return {}
    result = {}
    for key, value in where.items():
        if key == "$and":
            result["$and"] = [_translate_where_to_mongo(c) for c in value]
        elif key == "$or":
            result["$or"] = [_translate_where_to_mongo(c) for c in value]
        else:
            result[key] = value
    return result


class MongoDBVectorAdapter:
    """MongoDB Vector database adapter (singleton)

    Use an existing MongoDB connection to store vector data as document array fields.
    Similarity search is done on the Python side using numpy.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            try:
                from app.core.database import get_mongo_db_sync

                self._db = get_mongo_db_sync()
                logger.info("✅ MongoDB Vector adapter initialized successfully (Client cosine mode)")
                MongoDBVectorAdapter._initialized = True
            except Exception as e:
                logger.error(f"❌ MongoDB Vector adapter initialization failed: {e}")
                raise

    def get_or_create_collection(self, collection_name: str, vector_size: int = 1024):
        """Get or create a collection"""
        return MongoDBVectorCollection(self._db, collection_name, vector_size)

    def delete_collection(self, collection_name: str) -> bool:
        """Delete collection"""
        try:
            self._db.drop_collection(collection_name)
            logger.info(f"✅ MongoDB Collection deleted: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Deleting MongoDB collection failed: {e}")
            return False

    def list_collections(self) -> List[Dict[str, Any]]:
        """List all vector collections and their information"""
        result = []
        try:
            for name in self._db.list_collection_names():
                if name.startswith("system."):
                    continue
                try:
                    count = self._db[name].count_documents({})
                    result.append({
                        "name": name,
                        "point_count": count,
                        "dimensions": 0,  # Dimensions are not cached, read on demand
                    })
                except Exception:
                    result.append({"name": name, "point_count": 0, "dimensions": 0})
        except Exception as e:
            logger.error(f"❌ MongoDB Listing collection failed: {e}")
        return result

    def get_backend_name(self) -> str:
        return "mongodb"


class MongoDBVectorCollection:
    """MongoDB Collection wrapper class that implements the same interface as QdrantCollection.

    Document structure (flat, consistent with Qdrant payload):
    {
        "_id": "uuid-string",
        "embedding": [0.1, 0.2, ...],   # vector array
        "document": "text content",
        "title": "...",
        "manual_type": "...",
        ...Other metadata fields
    }
    """

    def __init__(self, db, collection_name: str, vector_size: int):
        self._db = db
        self._collection_name = collection_name
        self._vector_size = vector_size
        self._collection = db[collection_name]

        # Make sure the collection exists (MongoDB automatically creates it on first write, here only the index is created)
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes (idempotent operation)"""
        try:
            # Create a text index on the document field (optional, for future expansion)
            # MongoDB automatically has an index on _id
            pass  # MongoDB Automatically manage _id index
        except Exception as e:
            logger.debug(f"[MongoDB Vector] Index creation skipped: {e}")

    def add(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str],
    ) -> bool:
        """Add document (upsert semantics, idempotent)"""
        try:
            operations = []
            for doc_id, embedding, metadata, document in zip(ids, embeddings, metadatas, documents):
                # Build documentation:embedding + document + metadata (flat structure)
                doc = {
                    "embedding": embedding,
                    "document": document,
                }
                # Tile metadata fields to the top level of the document
                for k, v in metadata.items():
                    doc[k] = v

                operations.append(
                    UpdateOne(
                        {"_id": doc_id},
                        {"$set": doc},
                        upsert=True,
                    )
                )

            if operations:
                result = self._collection.bulk_write(operations, ordered=False)
                logger.debug(
                    f"✅ [MongoDB] Document added successfully "
                    f"(collection={self._collection_name}, "
                    f"upserted={result.upserted_count}, modified={result.modified_count})"
                )
            return True

        except Exception as e:
            logger.error(f"❌ [MongoDB] Failed to add document: {e}")
            return False

    def delete_ids(self, ids: List[str]) -> bool:
        """Delete document by ID"""
        if not ids:
            return True
        try:
            result = self._collection.delete_many({"_id": {"$in": ids}})
            logger.debug(
                f"✅ [MongoDB] Document deleted successfully "
                f"(collection={self._collection_name}, deleted={result.deleted_count})"
            )
            return True
        except Exception as e:
            logger.error(f"❌ [MongoDB] Failed to delete document: {e}")
            return False

    def delete(self, ids: List[str]) -> bool:
        """delete_ids Aliases for (ChromaDB style compatible)"""
        return self.delete_ids(ids)

    def get(self, ids: List[str]) -> Dict[str, Any]:
        """Batch retrieve documents by ID

        Return format:
            {"documents": [...], "metadatas": [...], "ids": [...]}
        """
        if not ids:
            return {"documents": [], "metadatas": [], "ids": []}
        try:
            cursor = self._collection.find(
                {"_id": {"$in": ids}},
                {"embedding": 0},  # Does not return embedding (consistent with Qdrant get)
            )
            documents = []
            metadatas = []
            result_ids = []
            for doc in cursor:
                document = doc.pop("document", "")
                doc_id = doc.pop("_id", "")
                # The remaining fields are as metadata
                metadata = {k: v for k, v in doc.items() if k not in ("document", "_id", "embedding")}
                documents.append(document)
                metadatas.append(metadata)
                result_ids.append(doc_id)
            return {
                "documents": documents,
                "metadatas": metadatas,
                "ids": result_ids,
            }
        except Exception as e:
            logger.error(f"❌ [MongoDB] get Retrieval failed: {e}")
            return {"documents": [], "metadatas": [], "ids": []}

    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Vector similarity search (client cosine)

        Process:
        1. Read all documents (including embedding) from MongoDB, optional where filtering
        2. Use numpy to calculate cosine similarity on the Python side
        3. Return top-k results

        The return format is consistent with QdrantCollection.query:
            {"documents": [[...]], "metadatas": [[...]], "distances": [[...]]}
        """
        try:
            if not query_embeddings:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            query_vector = np.array(query_embeddings[0], dtype=np.float32)

            # Build MongoDB query filters
            mongo_filter = _translate_where_to_mongo(where)

            # Read all documents from MongoDB, excluding embedding to save bandwidth but still required on Python side embedding
            # Note: All fields must be returned (including metadata such as title/provider/...),
            # Otherwise, the metadata in the search results will be lost, causing filtering to fail.
            cursor = self._collection.find(mongo_filter)

            docs = list(cursor)
            if not docs:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            # Build vector matrix
            vectors = []
            valid_docs = []
            for doc in docs:
                emb = doc.get("embedding")
                if emb is None or len(emb) == 0:
                    continue
                # skip zero vector (signed point)
                if all(v == 0.0 for v in emb):
                    continue
                vectors.append(emb)
                valid_docs.append(doc)

            if not valid_docs:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            matrix = np.array(vectors, dtype=np.float32)

            # Calculate cosine similarity
            # cosine = dot(a, b) / (||a|| * ||b||)
            query_norm = np.linalg.norm(query_vector)
            if query_norm == 0:
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            matrix_norms = np.linalg.norm(matrix, axis=1)
            # avoid division by zero
            valid_norms = matrix_norms > 0
            if not np.any(valid_norms):
                return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

            # Only calculate the similarity of valid vectors
            valid_matrix = matrix[valid_norms]
            valid_docs_filtered = [d for d, v in zip(valid_docs, valid_norms) if v]
            valid_norms_filtered = matrix_norms[valid_norms]

            similarities = np.dot(valid_matrix, query_vector) / (valid_norms_filtered * query_norm)

            # Sort in descending order of similarity, take top-k
            top_k = min(n_results, len(similarities))
            top_indices = np.argsort(similarities)[::-1][:top_k]

            documents = []
            metadatas = []
            distances = []

            for idx in top_indices:
                doc = valid_docs_filtered[idx]
                document = doc.get("document", "")

                # Re-read the complete metadata (only some fields were taken during query)
                # In order to avoid secondary queries, this is constructed from existing data
                metadata = {k: v for k, v in doc.items() if k not in ("_id", "embedding", "document")}
                # _id as doc_id
                metadata.setdefault("doc_id", str(doc.get("_id", "")))

                documents.append(document)
                metadatas.append(metadata)
                # distance = 1 - similarity (Consistent with Qdrant COSINE)
                distances.append(float(1.0 - similarities[idx]))

            return {
                "documents": [documents],
                "metadatas": [metadatas],
                "distances": [distances],
            }

        except Exception as e:
            logger.error(f"❌ [MongoDB] Query failed: {e}")
            return {"documents": [[]], "metadatas": [[]], "distances": [[]]}

    def count(self) -> int:
        """Get the number of documents"""
        try:
            return self._collection.count_documents({})
        except Exception as e:
            logger.error(f"❌ [MongoDB] Failed to get the number of documents: {e}")
            return 0

    def delete_collection(self) -> bool:
        """Delete collection"""
        try:
            self._db.drop_collection(self._collection_name)
            logger.info(f"✅ [MongoDB] Collection deleted: {self._collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ [MongoDB] Failed to delete collection: {e}")
            return False

    def get_backend_name(self) -> str:
        return "mongodb"
