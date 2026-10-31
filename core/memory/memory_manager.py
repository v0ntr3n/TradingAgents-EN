"""
Memory Manager v2.0

A memory system that supports multiple vector database backends for storing and retrieving the Agent s historical experience.

Supported backends:
- MongoDB (By default, it is stored uniformly with business data, and the client cosine similarity)
- Qdrant (Optional fallback, server mode is suitable for large data volumes)
- ChromaDB (There are thread safety issues, not recommended)

Features:
- Supports independent memory spaces for multiple Agents
- Memory retrieval based on semantic similarity
- Automatically manage vector database collections
- Integrate with EmbeddingManager
- Switching backends via environment variables
"""

import logging
import os
import queue
import asyncio
import threading
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)


_MEM0_COMPAT_DEFAULT_USER_ID = "legacy_tradingagents"
_AGENT_ID_ALIAS_MAPPING = {
    "bull_researcher": ["bull_researcher_v2", "bull_researcher"],
    "bull_researcher_v2": ["bull_researcher_v2", "bull_researcher"],
    "bear_researcher": ["bear_researcher_v2", "bear_researcher"],
    "bear_researcher_v2": ["bear_researcher_v2", "bear_researcher"],
    "trader": ["trader_v2", "trader"],
    "trader_v2": ["trader_v2", "trader"],
    "research_manager": ["research_manager_v2", "research_manager"],
    "research_manager_v2": ["research_manager_v2", "research_manager"],
    "risk_manager": ["risk_manager_v2", "risk_manager"],
    "risk_manager_v2": ["risk_manager_v2", "risk_manager"],
}


def _is_truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _run_async_sync(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}
    done = threading.Event()

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:  # pragma: no cover - Only used for cross-thread exception propagation
            error["value"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    done.wait()
    if "value" in error:
        raise error["value"]
    return result.get("value")


class Mem0AgentMemory:
    """Provides mem0 compatibility layer for v2 AgentMemory interface."""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.agent_ids = list(dict.fromkeys(_AGENT_ID_ALIAS_MAPPING.get(agent_id, [agent_id])))

    def _resolve_user_id(self) -> str:
        return str(os.getenv("MEM0_COMPAT_USER_ID") or _MEM0_COMPAT_DEFAULT_USER_ID).strip() or _MEM0_COMPAT_DEFAULT_USER_ID

    @staticmethod
    def _normalize_store_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(metadata or {})
        ticker = str(merged.get("ticker") or merged.get("symbol") or "").strip().upper()
        if ticker:
            merged["ticker"] = ticker
            merged.setdefault("symbol", ticker)
            merged.setdefault("object_type", "stock")
            merged.setdefault("object_key", ticker)
        merged.setdefault("source", "legacy_agent_memory_runtime")
        regime = str(merged.get("market_regime") or "unknown").strip().lower()
        if regime not in ("bull", "bear", "sideways", "unknown"):
            regime = "unknown"
        merged["market_regime"] = regime
        merged["volatility_quintile"] = max(1, min(5, int(merged.get("volatility_quintile", 3))))
        role = str(merged.get("attribution_role") or "neutral").strip().lower()
        if role not in ("correct_driver", "overridden_correct", "false_driver", "correct_dissent_ignored", "neutral"):
            role = "neutral"
        merged["attribution_role"] = role
        if "brier_calibration_error" in merged:
            merged["brier_calibration_error"] = float(merged["brier_calibration_error"])
        return merged

    @staticmethod
    def filter_and_rerank_by_regime(
        memories: List[Dict[str, Any]],
        current_regime: Optional[str] = None,
        drawdown_circuit_breaker: bool = False,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Apply regime-aware filtering and re-ranking:
        - If drawdown_circuit_breaker is True, suspend retrieval (return []) to prevent anchoring bias.
        - Exclude memories from the opposite regime ('bull' vs 'bear').
        - Boost similarity by 1.5x for memories matching current_regime.
        """
        if drawdown_circuit_breaker:
            return []
        if not memories:
            return []
        if not current_regime or current_regime.lower() not in ("bull", "bear", "sideways"):
            return memories[:n_results]

        curr = current_regime.lower()
        opposite = {"bull": "bear", "bear": "bull"}.get(curr)

        filtered = []
        for item in memories:
            meta = item.get("metadata") or {}
            mem_regime = str(meta.get("market_regime", "unknown")).lower()
            if opposite and mem_regime == opposite:
                continue
            base_sim = float(item.get("similarity", 0.5))
            boosted_sim = min(1.0, base_sim * 1.5) if mem_regime == curr else base_sim
            updated = dict(item)
            updated["similarity"] = round(boosted_sim, 6)
            updated["distance"] = round(max(0.0, 1.0 - boosted_sim), 6)
            filtered.append(updated)

        filtered.sort(key=lambda x: x["similarity"], reverse=True)
        return filtered[:n_results]

    @staticmethod
    def _normalize_recall_filters(filter_metadata: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not filter_metadata:
            return None
        merged = dict(filter_metadata)
        ticker = str(merged.get("ticker") or merged.get("symbol") or "").strip().upper()
        if ticker:
            merged["ticker"] = ticker
            merged.setdefault("symbol", ticker)
        return merged

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None,
    ) -> bool:
        del memory_id
        try:
            from .service import get_memory_service

            svc = get_memory_service()
            result = _run_async_sync(
                svc.store(
                    [{"role": "user", "content": str(content or "")}],
                    user_id=self._resolve_user_id(),
                    agent_id=self.agent_ids[0],
                    session_id=str((metadata or {}).get("ticker") or self.agent_id),
                    scope="agent_experience",
                    metadata=self._normalize_store_metadata(metadata),
                    infer=False,
                )
            )
            if result.success:
                logger.info("✅ mem0 AgentMemory Write successfully agent_id=%s", self.agent_ids[0])
                return True
            raise RuntimeError(result.error or "mem0 store failed")
        except Exception as exc:
            logger.warning("⚠️ mem0 AgentMemory Write failed %s: %s", self.agent_id, exc)
        return False

    def search_memories(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
        current_regime: Optional[str] = None,
        drawdown_circuit_breaker: bool = False,
    ) -> List[Dict[str, Any]]:
        if drawdown_circuit_breaker:
            return []
        try:
            from .service import get_memory_service

            svc = get_memory_service()
            memories: List[Dict[str, Any]] = []
            seen_memory_ids = set()
            normalized_filters = self._normalize_recall_filters(filter_metadata)
            for agent_id in self.agent_ids:
                recalled = _run_async_sync(
                    svc.recall(
                        query=str(query or ""),
                        user_id=self._resolve_user_id(),
                        agent_id=agent_id,
                        scopes=["agent_experience"],
                        metadata_filters=normalized_filters,
                        limit=n_results,
                    )
                )
                for item in recalled or []:
                    memory_id = getattr(item, "id", None)
                    if memory_id and memory_id in seen_memory_ids:
                        continue
                    if memory_id:
                        seen_memory_ids.add(memory_id)
                    memories.append({
                        "content": item.metadata.get("legacy_situation") or item.memory,
                        "metadata": item.metadata,
                        "similarity": item.score,
                        "distance": max(0.0, 1.0 - float(item.score or 0.0)),
                    })
                    if len(memories) >= n_results:
                        break
                if len(memories) >= n_results:
                    break
            if memories:
                memories = self.filter_and_rerank_by_regime(
                    memories,
                    current_regime=current_regime,
                    drawdown_circuit_breaker=drawdown_circuit_breaker,
                    n_results=n_results,
                )
                logger.info("✅ mem0 AgentMemory hit agent_id=%s recalled=%d aliases=%s", self.agent_id, len(memories), self.agent_ids)
                return memories
            logger.info("📭 mem0 AgentMemory miss agent_id=%s aliases=%s", self.agent_id, self.agent_ids)
        except Exception as exc:
            logger.warning("⚠️ mem0 AgentMemory Recall failed %s: %s", self.agent_id, exc)
        return []

    def get_memory_count(self) -> int:
        return 0

    def clear_memories(self):
        return None


class VectorStoreManager:
    """
    Vector database manager (singleton)

    Supports multiple backends:
    - mongodb (By default, it is stored uniformly with business data, and the client cosine similarity)
    - qdrant (Optional fallback, server mode is suitable for large data volumes)
    - chromadb (There are thread safety issues, not recommended)

    Switch the backend through the environment variable VECTOR_STORE_BACKEND
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(VectorStoreManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            # Read backend configuration (mongodb is used by default, reducing operation and maintenance components)
            backend = os.getenv("VECTOR_STORE_BACKEND", "mongodb").lower()
            self.backend = backend

            try:
                if backend == "mongodb":
                    from .mongodb_vector_adapter import MongoDBVectorAdapter
                    self._adapter = MongoDBVectorAdapter()
                    logger.info("✅ Vector database backend: MongoDB (Client cosine, unified storage with business data)")
                elif backend == "qdrant":
                    from .qdrant_adapter import QdrantAdapter
                    self._adapter = QdrantAdapter()
                    logger.info("✅ Vector database backend: Qdrant (Thread safety)")
                elif backend == "chromadb":
                    from .chromadb_adapter import ChromaDBAdapter
                    self._adapter = ChromaDBAdapter()
                    logger.warning("⚠️ Vector database backend: ChromaDB (There are thread safety issues, not recommended)")
                else:
                    logger.error(f"❌ Unsupported vector database backend: {backend}, Use default MongoDB")
                    from .mongodb_vector_adapter import MongoDBVectorAdapter
                    self._adapter = MongoDBVectorAdapter()
                    self.backend = "mongodb"

                VectorStoreManager._initialized = True

            except ImportError as e:
                logger.error(f"❌ Vector database backend initialization failed: {e}")
                raise

    def get_or_create_collection(self, name: str, vector_size: int = 1024):
        """
        Get or create a collection

        Args:
            name: Collection name
            vector_size: Vector dimension (default 1024, compatible with more embedding models)

        Returns:
            Collection object (implements VectorStoreInterface)
        """
        return self._adapter.get_or_create_collection(name, vector_size)

    def delete_collection(self, name: str) -> bool:
        """
        Delete collection

        Args:
            name: Collection name

        Returns:
            Is it successful?
        """
        return self._adapter.delete_collection(name)


class AgentMemory:
    """
    Agent memory manager

    Provide memory storage and retrieval capabilities for a single Agent.

    Memory writing (add_memory) is an asynchronous non-blocking operation:
    - call add_memory() Will submit the task to the background queue and return immediately
    - The background daemon thread processes the embedding generation in the queue in sequence. + vector storage
    - Avoid the main analysis process being blocked by embedding API calls and disk writes
    """

    # Background worker threads and queues shared by all AgentMemory instances (save thread resources)
    _shared_queue: Optional[queue.Queue] = None
    _shared_worker: Optional[threading.Thread] = None
    _shared_lock = threading.Lock()

    def __init__(self, agent_id: str, embedding_manager):
        """
        Initialize Agent memory

        Args:
            agent_id: Agent ID (used as vector database collection names)
            embedding_manager: EmbeddingManager Example
        """
        self.agent_id = agent_id
        self.embedding_manager = embedding_manager

        # Get or create a vector database collection
        self.vector_store_manager = VectorStoreManager()

        # Get embedding dimensions
        vector_size = 1024  # 🔥 Default dimension 1024 (compatible with more models)
        if hasattr(embedding_manager, 'get_embedding_dimension'):
            vector_size = embedding_manager.get_embedding_dimension()

        self.collection = self.vector_store_manager.get_or_create_collection(
            f"memory_{agent_id}",
            vector_size=vector_size
        )

        backend = self.vector_store_manager.backend
        logger.info(f"🧠 Initialize Agent memory: {agent_id} (backend: {backend})")

        # Make sure the shared background worker thread is started
        self._ensure_worker_started()

    @classmethod
    def _ensure_worker_started(cls):
        """Make sure the shared background worker thread is started (thread safe)"""
        if cls._shared_worker is not None and cls._shared_worker.is_alive():
            return
        with cls._shared_lock:
            if cls._shared_worker is not None and cls._shared_worker.is_alive():
                return
            cls._shared_queue = queue.Queue(maxsize=500)
            cls._shared_worker = threading.Thread(
                target=cls._worker_loop,
                name="memory-save-worker",
                daemon=True,
            )
            cls._shared_worker.start()
            logger.info("🚀 Memory background saving thread has been started")

    @classmethod
    def _worker_loop(cls):
        """Background thread: continue to fetch tasks from the queue and perform synchronous writing"""
        while True:
            try:
                task = cls._shared_queue.get()
                if task is None:
                    # Receive sentinel value, exit
                    logger.info("🛑 The memory background saving thread receives the exit signal")
                    break
                agent_memory, content, metadata, memory_id = task
                agent_memory._do_add_memory(content, metadata, memory_id)
            except Exception as e:
                logger.error(f"❌ Memory background saving thread exception: {e}", exc_info=True)
            finally:
                try:
                    cls._shared_queue.task_done()
                except ValueError:
                    pass

    def add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None
    ) -> bool:
        """
        Add memory (non-blocking)

        Submit the task to the background queue and return immediately. The background thread is responsible for the actual
        embedding Generation and vector storage operations.

        Args:
            content: Memory content (text)
            metadata: Metadata (such as time, ticker, etc.)
            memory_id: Memory ID (optional, automatically generated by default)

        Returns:
            Whether successfully joined the team (True=Submitted,False=Queue is full or abnormal)
        """
        try:
            self._ensure_worker_started()
            self._shared_queue.put_nowait((self, content, metadata, memory_id))
            logger.debug(f"📨 The memory has been submitted to the background queue: {self.agent_id} (queue length: {self._shared_queue.qsize()})")
            return True
        except queue.Full:
            logger.warning(f"⚠️ Memory save queue is full, skipping: {self.agent_id}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to commit memory to queue: {e}")
            return False

    def _do_add_memory(
        self,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        memory_id: Optional[str] = None
    ) -> bool:
        """
        actually performs the memory write (called in a background thread)

        Args:
            content: Memory content (text)
            metadata: metadata
            memory_id: memory ID
        """
        try:
            # get embedding
            embedding, provider = self.embedding_manager.get_embedding(content)
            if embedding is None:
                logger.warning(f"⚠️ Unable to obtain embedding, skipping memory storage")
                return False

            # generate ID
            if memory_id is None:
                import hashlib
                import time
                memory_id = hashlib.md5(f"{content[:100]}_{time.time()}".encode()).hexdigest()

            # Prepare metadata
            if metadata is None:
                metadata = {}
            metadata["agent_id"] = self.agent_id
            metadata["provider"] = provider

            # Store to vector database (thread safety is handled internally in the adapter)
            self.collection.add(
                documents=[content],
                embeddings=[embedding],
                metadatas=[metadata],
                ids=[memory_id]
            )

            logger.debug(f"✅ memory stored: {self.agent_id}, ID={memory_id[:8]}...")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to store memory: {e}")
            return False

    def search_memories(
        self,
        query: str,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for similar memories

        Args:
            query: Query text
            n_results: Number of results returned
            filter_metadata: Metadata filters

        Returns:
            Memory list, each memory contains content, metadata, similarity
        """
        try:
            # Get the query embedding
            query_embedding, provider = self.embedding_manager.get_embedding(query)
            if query_embedding is None:
                logger.warning(f"⚠️ Unable to get query embedding")
                return []

            # 🔥 Important: Make sure to use the same Embedding model when querying as when storing
            #
            # Reason:
            # 1. The vector dimensions of different models may be different (DashScope 1024 dimensions, OpenAI 1536 dimensions, etc.)
            # 2. Different models have different semantic spaces and cannot query each other even if they have the same dimensions.
            # 3. Accurate similarity calculations are only possible using vectors generated by the same model
            #
            # Solution: Add provider filtering to metadata filtering and only query memories using the same provider
            if filter_metadata is None:
                filter_metadata = {}

            # 🔥 Add provider filtering to ensure that only memories using the same Embedding model are queried
            # Note:
            # - If there are memories in the collection that use different providers, they will be filtered out
            # - This means that after switching the Embedding model, only the memory stored using the new model can be queried
            # - The memory of the old model still exists, but will not be queried (unless switching back to the old model)
            filter_metadata["provider"] = provider

            logger.debug(f"🔍 Query memory (using {provider} Embedding Model, only query the memory of the same provider)")

            # 🔥 Fix ChromaDB query syntax issue
            # ChromaDB The where query syntax requires:
            # - Single condition:{"key": "value"}
            # - Multiple conditions:{"$and": [{"key1": "value1"}, {"key2": "value2"}]}
            # You cannot directly pass a dictionary containing multiple keys
            where_clause = None
            if len(filter_metadata) == 1:
                # Single condition, used directly
                key, value = next(iter(filter_metadata.items()))
                where_clause = {key: value}
            elif len(filter_metadata) > 1:
                # For multiple conditions, use $and Operator
                where_clause = {
                    "$and": [{key: value} for key, value in filter_metadata.items()]
                }
            # If filter_metadata is empty and where_clause is None, no filtering will be performed

            # Check if the collection is empty (thread safety is handled internally in the adapter)
            count = self.collection.count()
            if count == 0:
                logger.debug(f"📭 Memory bank is empty: {self.agent_id}")
                return []

            # Adjust the number of results
            n_results = min(n_results, count)

            # Execute query
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
            }
            if where_clause is not None:
                query_kwargs["where"] = where_clause

            results = self.collection.query(**query_kwargs)

            # Format results
            memories = []
            if results and 'documents' in results and results['documents']:
                documents = results['documents'][0]
                metadatas = results.get('metadatas', [[]])[0]
                distances = results.get('distances', [[]])[0]

                for i, doc in enumerate(documents):
                    metadata = metadatas[i] if i < len(metadatas) else {}
                    distance = distances[i] if i < len(distances) else 1.0

                    memory = {
                        'content': doc,
                        'metadata': metadata,
                        'similarity': 1.0 - distance,  # Convert to similarity
                        'distance': distance
                    }
                    memories.append(memory)

                logger.debug(f"🔍 found {len(memories)} similar memories")

            return memories

        except Exception as e:
            logger.error(f"❌ Search memory failed: {e}")
            return []

    def get_memory_count(self) -> int:
        """Get the number of memories"""
        try:
            # Thread safety is handled internally in the adapter
            count = self.collection.count()
            return count
        except Exception as e:
            logger.error(f"❌ Failed to obtain memory quantity: {e}")
            return 0

    def clear_memories(self):
        """Clear all memories"""
        try:
            # Thread safety is handled internally in the adapter
            # Delete old collection
            self.vector_store_manager.delete_collection(f"memory_{self.agent_id}")

            # Recreate the collection
            vector_size = 1024  # 🔥 Default dimension 1024 (compatible with more models)
            if hasattr(self.embedding_manager, 'get_embedding_dimension'):
                vector_size = self.embedding_manager.get_embedding_dimension()

            self.collection = self.vector_store_manager.get_or_create_collection(
                f"memory_{self.agent_id}",
                vector_size=vector_size
            )
            logger.info(f"🗑️ clear memory: {self.agent_id}")
        except Exception as e:
            logger.error(f"❌ Failed to clear memory: {e}")


class MemoryManager:
    """
    global memory manager

    Manage memory instances for all Agents
    """

    def __init__(self, embedding_manager):
        """
        Initialize memory manager

        Args:
            embedding_manager: EmbeddingManager Example
        """
        self.embedding_manager = embedding_manager
        self._agent_memories: Dict[str, Any] = {}
        self._use_mem0_compat = str(os.getenv("MEMORY_USE_MEM0_COMPAT", "true")).strip().lower() in {"1", "true", "yes", "on"}
        # A3: mem0 Instance construction is not thread-safe (concurrent construction of AsyncMemory will deadlock),
        # get_agent_memory The check-then-create needs to be serialized (in the parallel start scenario, two researchers access the memory at the same time)
        self._memory_lock = threading.Lock()
        logger.info("🧠 Memory manager initialization completed")
        if not self._use_mem0_compat:
            logger.warning("⚠️ MemoryManager The legacy-only AgentMemory path is currently explicitly used, and it is recommended to move back to the mem0 main path.")

    def get_agent_memory(self, agent_id: str) -> Any:
        """
        Get the memory instance of the specified Agent (thread-safe: mem0 construction serialization)

        Args:
            agent_id: Agent ID

        Returns:
            AgentMemory Example
        """
        with self._memory_lock:
            if agent_id not in self._agent_memories:
                if self._use_mem0_compat:
                    self._agent_memories[agent_id] = Mem0AgentMemory(agent_id)
                else:
                    self._agent_memories[agent_id] = AgentMemory(agent_id, self.embedding_manager)

        return self._agent_memories[agent_id]

    def clear_all_memories(self):
        """Clear the memory of all Agents"""
        for agent_id, memory in self._agent_memories.items():
            memory.clear_memories()
        logger.info("🗑️ Clear all memories")

