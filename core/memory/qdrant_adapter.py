"""
Qdrant Vector database adapter

Features:
- Fully thread-safe (Rust implementation)
- Supports local mode (no server required)
- Automatic persistence
- Supports metadata filtering
"""

import logging
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class QdrantAdapter:
    """Qdrant Vector database adapter"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(QdrantAdapter, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            try:
                from qdrant_client import QdrantClient
                from qdrant_client.models import Distance, VectorParams, PointStruct, PointIdsList

                self.QdrantClient = QdrantClient
                self.Distance = Distance
                self.VectorParams = VectorParams
                self.PointStruct = PointStruct
                self.PointIdsList = PointIdsList

                # Determine data directory
                data_dir = os.getenv("QDRANT_DATA_DIR", "./data/qdrant")
                Path(data_dir).mkdir(parents=True, exist_ok=True)

                # Create local client
                self._client = QdrantClient(path=data_dir)
                logger.info(f"✅ Qdrant Client initialization successful (local mode: {data_dir})")

                # 🔧 Automatically repair meta.json: prevent collection registration loss due to concurrent writing or exceptions
                self._repair_meta_json(data_dir)

                QdrantAdapter._initialized = True

            except ImportError:
                logger.error("❌ Qdrant Not installed, please run: pip install qdrant-client")
                raise
            except Exception as e:
                logger.error(f"❌ Qdrant Initialization failed: {e}")
                raise

    def get_or_create_collection(self, collection_name: str, vector_size: int = 1024):
        """
        Get or create a collection

        Args:
            collection_name: Collection name
            vector_size: Vector dimension (default 1024, compatible with more embedding models)

        Returns:
            QdrantCollection Example
        """
        return QdrantCollection(self._client, collection_name, vector_size, self)

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete collection

        Args:
            collection_name: Collection name

        Returns:
            Is it successful?
        """
        try:
            self._client.delete_collection(collection_name)
            logger.info(f"✅ Qdrant Collection deleted: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Deleting Qdrant collection failed: {e}")
            return False

    def list_collections(self) -> List[Dict[str, Any]]:
        """List all collections and their information (reuse existing clients to avoid file lock conflicts)

        Returns:
            [{name, point_count, dimensions}, ...]
        """
        result = []
        try:
            for col in self._client.get_collections().collections:
                try:
                    info = self._client.get_collection(col.name)
                    result.append({
                        "name": col.name,
                        "point_count": info.points_count or 0,
                        "dimensions": info.config.params.vectors.size if info.config.params.vectors else 0,
                    })
                except Exception as e:
                    logger.warning(f"⚠️ Qdrant read collection {col.name} Message failed: {e}")
                    result.append({"name": col.name, "point_count": 0, "dimensions": 0})
        except Exception as e:
            logger.error(f"❌ Qdrant Listing collection failed: {e}")
        return result

    def get_raw_client(self):
        """Obtain the underlying QdrantClient instance (used for migration and other scenarios that require direct operation of the client)"""
        return self._client

    def _repair_meta_json(self, data_dir: str):
        """Automatically repair meta.json: Replace collections that exist on disk but are not registered in meta.json
        
        Prevent collection registration information from being lost due to concurrent writing, abnormal process exit, or Qdrant version upgrade.
        """
        import json, sqlite3, pickle

        meta_path = os.path.join(data_dir, "meta.json")
        collection_dir = os.path.join(data_dir, "collection")

        if not os.path.exists(meta_path) or not os.path.exists(collection_dir):
            return

        try:
            # Read current meta.json
            with open(meta_path, "r") as f:
                meta = json.load(f)

            registered = set(meta.get("collections", {}).keys())

            # Scan the disk for actual collection
            on_disk = set()
            for name in os.listdir(collection_dir):
                storage = os.path.join(collection_dir, name, "storage.sqlite")
                if os.path.exists(storage):
                    on_disk.add(name)

            # Find orphan collections (disks exist but are not registered)
            orphans = on_disk - registered
            if not orphans:
                return

            logger.warning(
                f"🔧 [Qdrant] discover {len(orphans)} Orphan collection (the disk exists but meta.json is not registered), which is being automatically repaired..."
            )

            for name in sorted(orphans):
                storage = os.path.join(collection_dir, name, "storage.sqlite")
                dims = 1024  # Default dimensions
                try:
                    conn = sqlite3.connect(storage)
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM points")
                    cnt = cur.fetchone()[0]
                    if cnt > 0:
                        cur.execute("SELECT point FROM points LIMIT 1")
                        row = cur.fetchone()
                        if row and row[0]:
                            point = pickle.loads(row[0])
                            dims = len(point.vector)
                    conn.close()
                except Exception:
                    pass

                meta["collections"][name] = {
                    "vectors": {
                        "size": dims, "distance": "Cosine",
                        "hnsw_config": None, "quantization_config": None,
                        "on_disk": None, "datatype": None, "multivector_config": None
                    },
                    "shard_number": None, "sharding_method": None,
                    "replication_factor": None, "write_consistency_factor": None,
                    "on_disk_payload": None, "hnsw_config": None,
                    "wal_config": None, "optimizers_config": None,
                    "quantization_config": None, "sparse_vectors": None,
                    "strict_mode_config": None, "metadata": None
                }
                logger.info(f"  ✅ Fixed: {name} ({dims}d)")

            # write back meta.json
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
            logger.info(f"🔧 [Qdrant] meta.json Repair completed, restored {len(orphans)} a collection")

        except Exception as e:
            logger.warning(f"⚠️ [Qdrant] meta.json Fix check failure (ignored, does not affect startup): {e}")


class QdrantCollection:
    """Qdrant Collection wrapper class, implementation VectorStoreInterface"""

    def __init__(self, client, collection_name: str, vector_size: int, adapter):
        self.client = client
        self.collection_name = collection_name
        self.vector_size = vector_size
        self.adapter = adapter

        # Check if the collection exists
        collection_exists = False
        need_recreate = False

        try:
            collection_info = self.client.get_collection(collection_name)
            collection_exists = True

            # 🔥 Check if vector dimensions match
            existing_vector_size = collection_info.config.params.vectors.size
            if existing_vector_size != vector_size:
                logger.warning(
                    f"⚠️ Qdrant collection {collection_name} The vector dimensions of do not match!"
                    f"Existing: {existing_vector_size}, need: {vector_size}"
                )
                logger.info(f"🔄 The collection will be deleted and recreated...")
                need_recreate = True
            else:
                logger.debug(f"📂 Qdrant Collection already exists: {collection_name} (vector dimensions: {existing_vector_size})")
        except Exception as e:
            # Collection does not exist
            logger.debug(f"📂 Qdrant Collection does not exist: {collection_name}, New collection will be created")

        # If you need to recreate it, delete the old collection first
        if need_recreate:
            try:
                self.client.delete_collection(collection_name)
                logger.info(f"🗑️ Old collection deleted: {collection_name} (Dimensions: {existing_vector_size} -> {vector_size})")
                collection_exists = False
            except Exception as e:
                # 🔥 Improvement: try to continue creating even if deletion fails (possible overwriting)
                logger.warning(f"⚠️ Failed to delete old collection: {e}, Will try to create the new collection directly (may fail)")
                # Don't raise, keep trying to create

        # Create a new collection if it does not exist
        if not collection_exists or need_recreate:
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=adapter.VectorParams(
                    size=vector_size,
                    distance=adapter.Distance.COSINE
                )
            )
            logger.info(f"✅ Qdrant Collection created: {collection_name} (vector dimensions: {vector_size})")

    def add(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> bool:
        """Add document"""
        try:
            logger.debug(f"🔒 [Qdrant] Prepare to add documents (collection={self.collection_name}, count={len(documents)})")

            # Build Qdrant points
            points = []
            for i, (doc_id, embedding, metadata, document) in enumerate(zip(ids, embeddings, metadatas, documents)):
                # Save the document content as well payload
                payload = metadata.copy()
                payload["document"] = document

                point = self.adapter.PointStruct(
                    id=doc_id,
                    vector=embedding,
                    payload=payload
                )
                points.append(point)

            # Bulk upload
            self.client.upsert(
                collection_name=self.collection_name,
                points=points
            )

            logger.debug(f"✅ [Qdrant] Document added successfully (collection={self.collection_name}, count={len(documents)})")
            return True

        except Exception as e:
            logger.error(f"❌ [Qdrant] Failed to add document: {e}")
            return False

    def delete_ids(self, ids: List[str]) -> bool:
        """Delete points by document ID."""
        if not ids:
            return True
        try:
            logger.debug(f"🔒 [Qdrant] Prepare to delete documents by ID (collection={self.collection_name}, count={len(ids)})")
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=self.adapter.PointIdsList(points=ids),
            )
            logger.debug(f"✅ [Qdrant] Delete document by ID successfully (collection={self.collection_name}, count={len(ids)})")
            return True
        except Exception as e:
            logger.error(f"❌ [Qdrant] Delete document by ID failed: {e}")
            return False

    def delete(self, ids: List[str]) -> bool:
        """delete_ids Alias for (compatible with ChromaDB-style delete calls)."""
        return self.delete_ids(ids)

    def get(self, ids: List[str]) -> Dict[str, Any]:
        """Batch retrieval points by ID (ChromaDB style), used to read meta-information such as signature points.

        The return format is the same as query() Consistent:
            {
                "documents": [...],
                "metadatas": [...],
                "ids": [...],
            }
        IDs that do not exist will be skipped, and the returned result will only contain the actual hit points.
        """
        if not ids:
            return {"documents": [], "metadatas": [], "ids": []}
        try:
            # Qdrant In local mode, point ID is a UUID object and needs to be converted into a string.
            import uuid as uuid_module
            qdrant_ids = []
            for id_str in ids:
                try:
                    qdrant_ids.append(uuid_module.UUID(id_str))
                except (ValueError, AttributeError):
                    qdrant_ids.append(id_str)

            retrieved = self.client.retrieve(
                collection_name=self.collection_name,
                ids=qdrant_ids,
                with_payload=True,
                with_vectors=False,
            )
            documents = []
            metadatas = []
            result_ids = []
            for point in retrieved:
                payload = point.payload or {}
                # document exist payload["document"], with add() consistent
                document = payload.get("document", "")
                metadata = {k: v for k, v in payload.items() if k != "document"}
                documents.append(document)
                metadatas.append(metadata)
                result_ids.append(point.id)
            return {
                "documents": documents,
                "metadatas": metadatas,
                "ids": result_ids,
            }
        except Exception as e:
            logger.error(f"❌ [Qdrant] get Retrieval by ID failed (collection={self.collection_name}): {e}")
            return {"documents": [], "metadatas": [], "ids": []}

    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query similar documents"""
        try:
            logger.debug(f"🔒 [Qdrant] Prepare query (collection={self.collection_name}, n_results={n_results})")

            # Qdrant Only supports a single query vector, take the first one
            query_vector = query_embeddings[0] if query_embeddings else []

            # Build filter conditions
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            query_filter = None
            if where:
                # Convert ChromaDB-style where to Qdrant Filter
                conditions = []
                for key, value in where.items():
                    if key == "$and":
                        # Process $and Operator
                        for condition in value:
                            for k, v in condition.items():
                                conditions.append(
                                    FieldCondition(key=k, match=MatchValue(value=v))
                                )
                    else:
                        conditions.append(
                            FieldCondition(key=key, match=MatchValue(value=value))
                        )

                if conditions:
                    query_filter = Filter(must=conditions)

            # Perform a search (using the query_points method, the search method was removed in v1.16.0)
            search_results = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=n_results,
                query_filter=query_filter
            )

            logger.debug(f"✅ [Qdrant] Query successful (collection={self.collection_name}, results={len(search_results.points)})")

            # Convert to ChromaDB format
            documents = []
            metadatas = []
            distances = []

            for result in search_results.points:
                # Extract document content
                document = result.payload.get("document", "")
                documents.append(document)

                # Extract metadata (remove document field)
                metadata = {k: v for k, v in result.payload.items() if k != "document"}
                metadatas.append(metadata)

                # Qdrant What is returned is the similarity score (the higher, the more similar), converted into distance (the lower, the more similar)
                # For COSINE distance:distance = 1 - score
                distance = 1.0 - result.score
                distances.append(distance)

            return {
                'documents': [documents],  # ChromaDB The format is a two-dimensional array
                'metadatas': [metadatas],
                'distances': [distances]
            }

        except Exception as e:
            logger.error(f"❌ [Qdrant] Query failed: {e}")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

    def count(self) -> int:
        """Get the number of documents"""
        try:
            logger.debug(f"🔒 [Qdrant] Prepare to obtain the number of documents (collection={self.collection_name})")
            collection_info = self.client.get_collection(self.collection_name)
            count = collection_info.points_count
            logger.debug(f"✅ [Qdrant] Number of documents: {count}")
            return count
        except Exception as e:
            logger.error(f"❌ [Qdrant] Failed to get the number of documents: {e}")
            return 0

    def delete_collection(self) -> bool:
        """Delete collection"""
        try:
            logger.debug(f"🔒 [Qdrant] Prepare to delete collection (collection={self.collection_name})")
            self.client.delete_collection(self.collection_name)
            logger.debug(f"✅ [Qdrant] Collection deleted (collection={self.collection_name})")
            return True
        except Exception as e:
            logger.error(f"❌ [Qdrant] Failed to delete collection: {e}")
            return False

    def get_backend_name(self) -> str:
        """Get backend name"""
        return "qdrant"

