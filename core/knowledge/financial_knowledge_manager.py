"""
Financial Knowledge Manager

Based on VectorStoreManager + EmbeddingManager Realize the storage and semantic retrieval of knowledge in the financial field.
Used for RAG (Retrieval-Augmented Generation) dynamic knowledge injection.

Features:
- Reuse existing vector database infrastructure (Qdrant)
- Support CRUD operations for knowledge documents
- Semantic retrieval + Classification filter
- Graceful degradation (returns empty results when the vector library is unavailable, without blocking the analysis process)
- The search results are formatted as prompt injected text
"""

import hashlib
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Knowledge base vector collection name
KNOWLEDGE_COLLECTION_NAME = "knowledge_finance"

# Retrieve default parameters
DEFAULT_TOP_K = 3
DEFAULT_MAX_CHARS = 1500
RETRIEVE_TIMEOUT_SECONDS = 3.0


class KnowledgeDocument:
    """Knowledge document data structure"""

    def __init__(
        self,
        id: str,
        category: str,
        title: str,
        content: str,
        tags: Optional[List[str]] = None,
        priority: int = 5,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
    ):
        self.id = id
        self.category = category
        self.title = title
        self.content = content
        self.tags = tags or []
        self.priority = priority
        now = datetime.now().isoformat()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "KnowledgeDocument":
        return cls(
            id=data["id"],
            category=data.get("category", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            priority=data.get("priority", 5),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class KnowledgeSnippet:
    """Search result snippet"""

    def __init__(self, doc_id: str, title: str, content: str, category: str,
                 similarity: float, tags: List[str]):
        self.doc_id = doc_id
        self.title = title
        self.content = content
        self.category = category
        self.similarity = similarity
        self.tags = tags

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "content": self.content,
            "category": self.category,
            "similarity": round(self.similarity, 4),
            "tags": self.tags,
        }


class FinancialKnowledgeManager:
    """
    Financial knowledge manager (single case)

    Provides CRUD and semantic retrieval capabilities for knowledge documents.
    Bottom layer reuse VectorStoreManager + EmbeddingManager. 
    """

    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, db=None):
        if self._initialized:
            return
        self._db = db
        self._embedding_manager = None
        self._collection = None
        self._available = False
        self._init_backend()
        FinancialKnowledgeManager._initialized = True

    # ----------------------------------------------------------
    # initialization
    # ----------------------------------------------------------

    def _init_backend(self):
        """Initialize the vector database and Embedding backend"""
        try:
            from core.llm.embedding_manager import EmbeddingManager
            from core.memory.memory_manager import VectorStoreManager

            self._embedding_manager = EmbeddingManager(db=self._db)
            vector_size = self._embedding_manager.get_embedding_dimension()

            vs_manager = VectorStoreManager()
            self._collection = vs_manager.get_or_create_collection(
                KNOWLEDGE_COLLECTION_NAME, vector_size=vector_size
            )
            self._available = True
            logger.info(
                f"✅ [KnowledgeManager] Initialization successful "
                f"(collection: {KNOWLEDGE_COLLECTION_NAME}, Dimensions: {vector_size})"
            )
        except Exception as e:
            logger.warning(f"⚠️ [KnowledgeManager] Initialization failed, knowledge retrieval will not be available: {e}")
            self._available = False

    @property
    def available(self) -> bool:
        """Is knowledge retrieval available?"""
        return self._available

    # ----------------------------------------------------------
    # CRUD Operation
    # ----------------------------------------------------------

    def add_knowledge(self, doc: KnowledgeDocument) -> bool:
        """
        Add knowledge documents (idempotent, the same ID will be overwritten)

        Args:
            doc: knowledge document

        Returns:
            Is it successful?
        """
        if not self._available:
            logger.warning("⚠️ [KnowledgeManager] Not available, skip adding")
            return False

        try:
            embedding, provider = self._embedding_manager.get_embedding(doc.content)
            if embedding is None:
                logger.warning(f"⚠️ [KnowledgeManager] Unable to obtain embedding: {doc.id}")
                return False

            metadata = {
                "doc_id": doc.id,
                "category": doc.category,
                "title": doc.title,
                "tags": ",".join(doc.tags),
                "priority": doc.priority,
                "provider": provider,
                "created_at": doc.created_at,
                "updated_at": doc.updated_at,
            }

            # Qdrant Requires an ID in UUID format, converted deterministically with uuid5 (same as doc.id → same UUID)
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc.id))

            self._collection.add(
                documents=[doc.content],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[point_id],
            )
            logger.debug(f"✅ [KnowledgeManager] Knowledge has been added: {doc.id} ({doc.title})")
            return True

        except Exception as e:
            logger.error(f"❌ [KnowledgeManager] Failed to add knowledge: {e}")
            return False

    def add_knowledge_batch(self, docs: List[KnowledgeDocument]) -> int:
        """
        Add knowledge documents in batches

        Returns:
            Successfully added quantity
        """
        success = 0
        for doc in docs:
            if self.add_knowledge(doc):
                success += 1
        logger.info(f"📚 [KnowledgeManager] Batch addition completed: {success}/{len(docs)}")
        return success

    def get_count(self) -> int:
        """Get the number of knowledge documents"""
        if not self._available:
            return 0
        try:
            return self._collection.count()
        except Exception as e:
            logger.error(f"❌ [KnowledgeManager] Failed to get quantity: {e}")
            return 0

    def clear_all(self) -> bool:
        """Clear all knowledge documents"""
        if not self._available:
            return False
        try:
            from core.memory.memory_manager import VectorStoreManager

            vs_manager = VectorStoreManager()
            vs_manager.delete_collection(KNOWLEDGE_COLLECTION_NAME)

            vector_size = self._embedding_manager.get_embedding_dimension()
            self._collection = vs_manager.get_or_create_collection(
                KNOWLEDGE_COLLECTION_NAME, vector_size=vector_size
            )
            logger.info("🗑️ [KnowledgeManager] All knowledge has been cleared")
            return True
        except Exception as e:
            logger.error(f"❌ [KnowledgeManager] Clearing failed: {e}")
            return False

    # ----------------------------------------------------------
    # Semantic retrieval
    # ----------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int = DEFAULT_TOP_K,
        category: Optional[str] = None,
    ) -> List[KnowledgeSnippet]:
        """
        Semantic retrieval of knowledge documents

        Args:
            query: Query text
            top_k: Number of results returned
            category: Optional category filtering

        Returns:
            List of knowledge fragments (in descending order of similarity)
        """
        if not self._available:
            return []

        try:
            start_time = time.time()

            query_embedding, provider = self._embedding_manager.get_embedding(query)
            if query_embedding is None:
                logger.warning("⚠️ [KnowledgeManager] Unable to get query embedding")
                return []

            count = self._collection.count()
            if count == 0:
                logger.debug("📭 [KnowledgeManager] Knowledge base is empty")
                return []

            top_k = min(top_k, count)

            # Build filter conditions
            where_clause = None
            filter_parts = {"provider": provider}
            if category:
                filter_parts["category"] = category

            if len(filter_parts) == 1:
                key, value = next(iter(filter_parts.items()))
                where_clause = {key: value}
            else:
                where_clause = {
                    "$and": [{k: v} for k, v in filter_parts.items()]
                }

            results = self._collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where=where_clause,
            )

            elapsed = time.time() - start_time

            snippets: List[KnowledgeSnippet] = []
            if results and "documents" in results and results["documents"]:
                documents = results["documents"][0]
                metadatas = results.get("metadatas", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for i, doc_text in enumerate(documents):
                    meta = metadatas[i] if i < len(metadatas) else {}
                    dist = distances[i] if i < len(distances) else 1.0
                    similarity = 1.0 - dist

                    snippets.append(KnowledgeSnippet(
                        doc_id=meta.get("doc_id", ""),
                        title=meta.get("title", ""),
                        content=doc_text,
                        category=meta.get("category", ""),
                        similarity=similarity,
                        tags=meta.get("tags", "").split(",") if meta.get("tags") else [],
                    ))

            # Secondary sorting by priority (when similarities are similar, those with higher priority will be ranked first)
            snippets.sort(key=lambda s: (-s.similarity, -0))

            logger.debug(
                f"🔍 [KnowledgeManager] Search completed: "
                f"query='{query[:30]}...', results={len(snippets)}, "
                f"elapsed={elapsed:.2f}s"
            )
            return snippets

        except Exception as e:
            logger.error(f"❌ [KnowledgeManager] Retrieval failed: {e}")
            return []

    # ----------------------------------------------------------
    # Prompt Integrated interface
    # ----------------------------------------------------------

    def retrieve_for_prompt(
        self,
        question: str,
        top_k: int = DEFAULT_TOP_K,
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> str:
        """
        Retrieve knowledge and format it into prompt-injected text.

        This is the main integration interface with IntelligentAssistantService / PlannedAnalysisService.
        Returning an empty string indicates that no knowledge is available (downgraded to static knowledge).

        Args:
            question: User issues
            top_k: Search quantity
            max_chars: Maximum number of characters

        Returns:
            Formatted knowledge text (can be spelled directly into the system prompt), or an empty string
        """
        if not self._available:
            return ""

        try:
            snippets = self.search(question, top_k=top_k)
            if not snippets:
                return ""

            lines = [" [Dynamic knowledge reference]"]
            total_chars = len(lines[0])

            for s in snippets:
                entry = f"- **{s.title}**: {s.content}"
                if total_chars + len(entry) > max_chars:
                    break
                lines.append(entry)
                total_chars += len(entry)

            if len(lines) <= 1:
                return ""

            result = "\n".join(lines)
            logger.info(
                f"📚 [KnowledgeManager] Inject {len(lines) - 1} piece of knowledge "
                f"({total_chars} character) for: '{question[:30]}...'"
            )
            return result

        except Exception as e:
            logger.warning(f"⚠️ [KnowledgeManager] retrieve_for_prompt failed: {e}")
            return ""

    # ----------------------------------------------------------
    # Statistics
    # ----------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics"""
        return {
            "available": self._available,
            "collection_name": KNOWLEDGE_COLLECTION_NAME,
            "total_documents": self.get_count(),
            "backend": "qdrant" if self._available else "unavailable",
        }

