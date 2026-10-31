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
_CIRCUIT_BREAKER_AGENTS = {
    "bull_researcher",
    "bull_researcher_v2",
    "bear_researcher",
    "bear_researcher_v2",
    "research_manager",
    "research_manager_v2",
    "trader",
    "trader_v2",
    "risk_manager",
    "risk_manager_v2",
}


def circuit_breaker_memory_filter(
    memories: List[Dict[str, Any]],
    current_regime: str,
    regime_confidence: float = 1.0,
    agent_id: str = "",
) -> List[Dict[str, Any]]:
    """Filter memories according to regime circuit-breaker policy.

    For circuit-breaker agents (bull/bear researcher, manager, trader, risk manager):
    - When regime_confidence >= 0.5: filter out memories whose stored market_regime contradicts current_regime.
    - When regime_confidence < 0.5: bypass circuit-breaker (allowing cross-regime memory recall under regime ambiguity).
    For non-circuit agents:
    - Return memories unfiltered.
    """
    if agent_id and agent_id not in _CIRCUIT_BREAKER_AGENTS:
        return memories

    norm_regime = str(current_regime or "sideways").lower().strip()
    if norm_regime not in {"bull", "bear", "sideways"}:
        norm_regime = "sideways"

    try:
        conf = float(regime_confidence)
    except (ValueError, TypeError):
        conf = 1.0

    if conf < 0.5:
        # Ambiguous regime: bypass circuit breaker to preserve hedging memories
        return list(memories)

    filtered = []
    for item in memories:
        meta = item.get("metadata") if isinstance(item, dict) else getattr(item, "metadata", {})
        if not isinstance(meta, dict):
            meta = {}
        mem_regime = str(meta.get("market_regime") or "sideways").lower().strip()
        if mem_regime == norm_regime:
            filtered.append(item)

    return filtered


def _is_truthy(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _run_async_sync(coro):
    import inspect
    if not inspect.isawaitable(coro):
        return coro

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

        # Enforce mandatory R3 metadata keys
        regime = str(merged.get("market_regime") or "sideways").strip().lower()
        merged["market_regime"] = regime if regime in {"bull", "bear", "sideways"} else "sideways"

        try:
            vol = int(merged.get("volatility_quintile", 3))
            merged["volatility_quintile"] = max(1, min(5, vol))
        except (ValueError, TypeError):
            merged["volatility_quintile"] = 3

        try:
            brier = float(merged.get("brier_calibration_error", 0.0))
            merged["brier_calibration_error"] = max(0.0, brier)
        except (ValueError, TypeError):
            merged["brier_calibration_error"] = 0.0

        return merged

    @staticmethod
    def _normalize_recall_filters(filter_metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(filter_metadata or {})
        ticker = str(merged.get("ticker") or merged.get("symbol") or "").strip().upper()
        if ticker:
            merged["ticker"] = ticker
            merged.setdefault("symbol", ticker)

        regime = str(merged.get("market_regime") or "sideways").strip().lower()
        merged["market_regime"] = regime if regime in {"bull", "bear", "sideways"} else "sideways"

        try:
            vol = int(merged.get("volatility_quintile", 3))
            merged["volatility_quintile"] = max(1, min(5, vol))
        except (ValueError, TypeError):
            merged["volatility_quintile"] = 3

        try:
            brier = float(merged.get("brier_calibration_error", 0.0))
            merged["brier_calibration_error"] = max(0.0, brier)
        except (ValueError, TypeError):
            merged["brier_calibration_error"] = 0.0

        return merged

    circuit_breaker_memory_filter = staticmethod(circuit_breaker_memory_filter)

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
        state: Optional[Dict[str, Any]] = None,
        current_regime: Optional[str] = None,
        regime_confidence: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        try:
            from .service import get_memory_service

            svc = get_memory_service()
            memories: List[Dict[str, Any]] = []
            seen_memory_ids = set()
            normalized_filters = self._normalize_recall_filters(filter_metadata)

            # Resolve regime and confidence from parameters, state, or filter_metadata
            resolved_regime = current_regime
            resolved_conf = regime_confidence

            if state is not None and isinstance(state, dict):
                if resolved_regime is None:
                    resolved_regime = state.get("market_regime")
                if resolved_conf is None:
                    resolved_conf = state.get("regime_confidence")

            if filter_metadata is not None and isinstance(filter_metadata, dict):
                if resolved_regime is None:
                    resolved_regime = filter_metadata.get("current_regime") or filter_metadata.get("market_regime")
                if resolved_conf is None:
                    resolved_conf = filter_metadata.get("regime_confidence")
                if resolved_regime is None and isinstance(filter_metadata.get("state"), dict):
                    resolved_regime = filter_metadata["state"].get("market_regime")
                if resolved_conf is None and isinstance(filter_metadata.get("state"), dict):
                    resolved_conf = filter_metadata["state"].get("regime_confidence")

            resolved_regime = str(resolved_regime or normalized_filters.get("market_regime", "sideways")).strip().lower()
            if resolved_regime not in {"bull", "bear", "sideways"}:
                resolved_regime = "sideways"

            if resolved_conf is None:
                resolved_conf = 1.0
            else:
                try:
                    resolved_conf = float(resolved_conf)
                except (ValueError, TypeError):
                    resolved_conf = 1.0

            is_circuit_agent = any(aid in _CIRCUIT_BREAKER_AGENTS for aid in self.agent_ids)

            # Build backend metadata filters (for mem0 recall)
            # Only pass explicit non-regime filters (e.g. ticker/symbol) to svc.recall,
            # allowing cross-regime memory candidates to reach client-side circuit breaker.
            backend_filters = {}
            if filter_metadata:
                for k, v in filter_metadata.items():
                    if k in ("ticker", "symbol"):
                        backend_filters[k] = v
                    elif k not in ("market_regime", "current_regime", "regime_confidence", "state", "volatility_quintile", "brier_calibration_error"):
                        backend_filters[k] = v

            fetch_limit = max(n_results * 3, 15) if is_circuit_agent and resolved_conf >= 0.5 else n_results

            for agent_id in self.agent_ids:
                recalled = _run_async_sync(
                    svc.recall(
                        query=str(query or ""),
                        user_id=self._resolve_user_id(),
                        agent_id=agent_id,
                        scopes=["agent_experience"],
                        metadata_filters=backend_filters or None,
                        limit=fetch_limit,
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
                if len(memories) >= fetch_limit:
                    break

            if is_circuit_agent:
                memories = circuit_breaker_memory_filter(
                    memories,
                    current_regime=resolved_regime,
                    regime_confidence=resolved_conf,
                    agent_id=self.agent_id,
                )

            memories = memories[:n_results]

            if memories:
                logger.info("✅ mem0 AgentMemory hit agent_id=%s recalled=%d aliases=%s regime=%s conf=%.2f",
                            self.agent_id, len(memories), self.agent_ids, resolved_regime, resolved_conf)
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
            metadata = Mem0AgentMemory._normalize_store_metadata(metadata)
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
        filter_metadata: Optional[Dict[str, Any]] = None,
        state: Optional[Dict[str, Any]] = None,
        current_regime: Optional[str] = None,
        regime_confidence: Optional[float] = None,
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

            # Resolve regime and confidence
            resolved_regime = current_regime
            resolved_conf = regime_confidence

            if state is not None and isinstance(state, dict):
                if resolved_regime is None:
                    resolved_regime = state.get("market_regime")
                if resolved_conf is None:
                    resolved_conf = state.get("regime_confidence")

            if filter_metadata is not None and isinstance(filter_metadata, dict):
                if resolved_regime is None:
                    resolved_regime = filter_metadata.get("current_regime") or filter_metadata.get("market_regime")
                if resolved_conf is None:
                    resolved_conf = filter_metadata.get("regime_confidence")

            # 🔥 Important: Make sure to use the same Embedding model when querying as when storing
            backend_filter_metadata = dict(filter_metadata or {})
            backend_filter_metadata.pop("current_regime", None)
            backend_filter_metadata.pop("regime_confidence", None)
            backend_filter_metadata.pop("state", None)

            # 🔥 Add provider filtering to ensure that only memories using the same Embedding model are queried
            backend_filter_metadata["provider"] = provider

            logger.debug(f"🔍 Query memory (using {provider} Embedding Model, only query the memory of the same provider)")

            where_clause = None
            if len(backend_filter_metadata) == 1:
                key, value = next(iter(backend_filter_metadata.items()))
                where_clause = {key: value}
            elif len(backend_filter_metadata) > 1:
                where_clause = {
                    "$and": [{key: value} for key, value in backend_filter_metadata.items()]
                }

            # Check if the collection is empty (thread safety is handled internally in the adapter)
            count = self.collection.count()
            if count == 0:
                logger.debug(f"📭 Memory bank is empty: {self.agent_id}")
                return []

            # Adjust the number of results
            is_circuit_agent = self.agent_id in _CIRCUIT_BREAKER_AGENTS
            query_limit = min(max(n_results * 3, 15), count) if is_circuit_agent else min(n_results, count)

            # Execute query
            query_kwargs = {
                "query_embeddings": [query_embedding],
                "n_results": query_limit,
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

            if is_circuit_agent and resolved_regime:
                memories = circuit_breaker_memory_filter(
                    memories,
                    current_regime=resolved_regime,
                    regime_confidence=resolved_conf if resolved_conf is not None else 1.0,
                    agent_id=self.agent_id,
                )

            return memories[:n_results]

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

