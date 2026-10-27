"""
Vector database unified interface

Supports multiple vector database backends:
- ChromaDB (Default, but has thread safety issues)
- Qdrant (Recommended, thread safe)
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class VectorStoreInterface(ABC):
    """Vector database unified interface"""

    @abstractmethod
    def add(
        self,
        documents: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict[str, Any]],
        ids: List[str]
    ) -> bool:
        """
        Add document to vector database

        Args:
            documents: Document content list
            embeddings: vector list
            metadatas: metadata list
            ids: Document ID list

        Returns:
            Is it successful?
        """
        pass

    @abstractmethod
    def query(
        self,
        query_embeddings: List[List[float]],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Query similar documents

        Args:
            query_embeddings: Query vector list
            n_results: Number of results returned
            where: Metadata filters

        Returns:
            Query result dictionary, format:
            {
                'documents': [[doc1, doc2, ...]],
                'metadatas': [[meta1, meta2, ...]],
                'distances': [[dist1, dist2, ...]]
            }
        """
        pass

    @abstractmethod
    def count(self) -> int:
        """
        Get the number of documents

        Returns:
            Number of documents
        """
        pass

    @abstractmethod
    def delete_collection(self) -> bool:
        """
        Delete collection

        Returns:
            Is it successful?
        """
        pass

    @abstractmethod
    def delete_ids(self, ids: List[str]) -> bool:
        """
        Delete some documents in a collection by document ID

        Args:
            ids: Document ID list

        Returns:
            Is it successful?
        """
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """
        Get backend name

        Returns:
            backend name (chromadb, qdrant etc.)
        """
        pass

