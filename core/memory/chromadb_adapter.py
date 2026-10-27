"""
ChromaDB Vector database adapter

Features:
- Lightweight and easy to use
- Support local persistence

⚠️ Warning:
- Rust The extension is not thread-safe in a multi-threaded environment
- May cause Windows access violation to crash
- It is recommended to use Qdrant instead
"""

import logging
import threading
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ChromaDBAdapter:
    """ChromaDB Vector database adapter"""

    _instance = None
    _lock = threading.Lock()
    _initialized = False
    _chroma_operation_lock = threading.Lock()  # 🔒 ChromaDB Operation locks (protecting Rust extensions)

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ChromaDBAdapter, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            try:
                # Use optimized ChromaDB configuration (multiple configurations and downgrade scenarios will be tried internally)
                from .chromadb_config import get_optimal_chromadb_client
                self._client = get_optimal_chromadb_client()
                logger.info("✅ ChromaDB Client initialization successful")
            except ImportError:
                # Downgrade: Use default configuration
                logger.warning("⚠️ Unable to import chromadb_config, using default configuration")
                import chromadb
                from chromadb.config import Settings

                self._client = chromadb.Client(Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                ))
                logger.info("✅ ChromaDB Client initialization successful (default configuration)")

            ChromaDBAdapter._initialized = True

    def get_or_create_collection(self, collection_name: str, vector_size: int = 1024):
        """
        Get or create a collection

        Args:
            collection_name: Collection name
            vector_size: Vector dimensions (automatically detected by ChromaDB, this parameter is for compatibility only)

        Returns:
            ChromaDBCollection Example
        """
        collection = self._client.get_or_create_collection(name=collection_name)
        return ChromaDBCollection(collection, collection_name)

    def delete_collection(self, collection_name: str) -> bool:
        """
        Delete collection

        Args:
            collection_name: Collection name

        Returns:
            Is it successful?
        """
        try:
            with ChromaDBAdapter._chroma_operation_lock:
                self._client.delete_collection(name=collection_name)
            logger.info(f"✅ ChromaDB Collection deleted: {collection_name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete ChromaDB collection: {e}")
            return False


class ChromaDBCollection:
    """ChromaDB Collection wrapper class, implementation VectorStoreInterface"""

    def __init__(self, collection, collection_name: str):
        self.collection = collection
        self.collection_name = collection_name

    def add(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> bool:
        """Add document"""
        try:
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - add (collection={self.collection_name})")
            with ChromaDBAdapter._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - add (collection={self.collection_name})")
                self.collection.upsert(
                    documents=documents,
                    embeddings=embeddings,
                    metadatas=metadatas,
                    ids=ids
                )
                logger.debug(f"✅ [ChromaDB] add Operation completed (collection={self.collection_name}, count={len(documents)})")
            logger.debug(f"🔓 [ChromaDB] Lock released - add (collection={self.collection_name})")
            return True

        except Exception as e:
            logger.error(f"❌ [ChromaDB] Failed to add document: {e}")
            return False

    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Query similar documents"""
        try:
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - query (collection={self.collection_name})")
            with ChromaDBAdapter._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - query (collection={self.collection_name})")

                query_kwargs = {
                    "query_embeddings": query_embeddings,
                    "n_results": n_results,
                }
                if where is not None:
                    query_kwargs["where"] = where

                results = self.collection.query(**query_kwargs)
                logger.debug(f"✅ [ChromaDB] query Operation completed (collection={self.collection_name})")
            logger.debug(f"🔓 [ChromaDB] Lock released - query (collection={self.collection_name})")
            return results

        except Exception as e:
            logger.error(f"❌ [ChromaDB] Query failed: {e}")
            return {'documents': [[]], 'metadatas': [[]], 'distances': [[]]}

    def count(self) -> int:
        """Get the number of documents"""
        try:
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - count (collection={self.collection_name})")
            with ChromaDBAdapter._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - count (collection={self.collection_name})")
                count = self.collection.count()
                logger.debug(f"✅ [ChromaDB] count Operation completed (collection={self.collection_name}, count={count})")
            logger.debug(f"🔓 [ChromaDB] Lock released - count (collection={self.collection_name})")
            return count
        except Exception as e:
            logger.error(f"❌ [ChromaDB] Failed to get the number of documents: {e}")
            return 0

    def delete_collection(self) -> bool:
        """Delete collection"""
        try:
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - delete_collection (collection={self.collection_name})")
            with ChromaDBAdapter._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - delete_collection (collection={self.collection_name})")
                # ChromaDB The collection object does not have a delete method and needs to be deleted through the client
                # This is just marking, the actual deletion is done by ChromaDBAdapter.delete_collection
                logger.debug(f"✅ [ChromaDB] delete_collection Operation completed (collection={self.collection_name})")
            logger.debug(f"🔓 [ChromaDB] Lock released - delete_collection (collection={self.collection_name})")
            return True
        except Exception as e:
            logger.error(f"❌ [ChromaDB] Failed to delete collection: {e}")
            return False

    def delete_ids(self, ids: List[str]) -> bool:
        """Delete some documents from a collection by document ID."""
        if not ids:
            return True
        try:
            logger.debug(f"🔒 [ChromaDB] Prepare to acquire lock - delete_ids (collection={self.collection_name}, count={len(ids)})")
            with ChromaDBAdapter._chroma_operation_lock:
                logger.debug(f"🔓 [ChromaDB] Lock acquired - delete_ids (collection={self.collection_name})")
                self.collection.delete(ids=ids)
                logger.debug(f"✅ [ChromaDB] delete_ids Operation completed (collection={self.collection_name}, count={len(ids)})")
            logger.debug(f"🔓 [ChromaDB] Lock released - delete_ids (collection={self.collection_name})")
            return True
        except Exception as e:
            logger.error(f"❌ [ChromaDB] Delete document by ID failed: {e}")
            return False

    def get_backend_name(self) -> str:
        """Get backend name"""
        return "chromadb"

