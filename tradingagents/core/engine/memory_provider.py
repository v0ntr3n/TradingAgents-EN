# tradingagents/core/engine/memory_provider.py
"""
Memory provider

Memory instances required to manage various Agents:
- bull_memory: multi-researcher memory
- bear_memory: short researcher memory
- trader_memory: trader memory
- invest_judge_memory: Research manager memory
- risk_manager_memory: Risk control manager memory

Configuration source:
- memory_enabled: Whether to enable memory function
- llm_provider: LLM provider used (affects embedding model selection)
"""

import asyncio
import os
import re
import threading
from typing import Any, Dict, Optional

from tradingagents.utils.logging_init import get_logger

logger = get_logger("default")


# Memory Name to Agent ID mapping
# Supports both memory_name and agent_id as key
MEMORY_AGENT_MAPPING = {
    "bull_memory": ["bull_researcher_v2", "bull_researcher"],
    "bear_memory": ["bear_researcher_v2", "bear_researcher"],
    "trader_memory": ["trader_v2", "trader"],
    "invest_judge_memory": ["research_manager_v2", "research_manager"],
    "risk_manager_memory": ["risk_manager_v2", "risk_manager"],
    "risk_memory": ["risk_manager_v2", "risk_manager"],  # Alias
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


class Mem0CompatMemory:
    """Compatible with the old version of FinancialSituationMemory interface, unified reading and writing through mem0."""

    _DEFAULT_USER_ID = "legacy_tradingagents"

    def __init__(self, memory_name: str, config: Optional[Dict[str, Any]] = None):
        self.memory_name = memory_name
        self.config = config or {}
        self.agent_ids = list(dict.fromkeys(MEMORY_AGENT_MAPPING.get(memory_name, [memory_name])))
        self.agent_id = self.agent_ids[0]

    @staticmethod
    def _extract_symbol(text: str) -> str:
        content = str(text or "")
        match = re.search(r"\b(?:sh|sz|bj|hk)\.\d{5,6}\b|\b\d{6}(?:\.[A-Z]{2})?\b", content, re.IGNORECASE)
        return match.group(0).upper() if match else ""

    def _build_metadata(self, situation: str, recommendation: str) -> Dict[str, Any]:
        symbol = self._extract_symbol(situation) or self._extract_symbol(recommendation)
        metadata: Dict[str, Any] = {
            "source": "legacy_financial_situation_memory",
            "legacy_memory_name": self.memory_name,
            "legacy_recommendation": recommendation,
            "legacy_situation": situation,
        }
        if symbol:
            metadata["symbol"] = symbol
            metadata["object_type"] = "stock"
            metadata["object_key"] = symbol
        return metadata

    def _build_metadata_filters(self, current_situation: str) -> Optional[Dict[str, str]]:
        symbol = self._extract_symbol(current_situation)
        if symbol:
            return {"symbol": symbol}
        return None

    def _resolve_user_id(self) -> str:
        return str(self.config.get("user_id") or "").strip() or self._DEFAULT_USER_ID

    def _resolve_session_id(self, text: str = "") -> str:
        explicit = str(self.config.get("session_id") or self.config.get("thread_id") or "").strip()
        if explicit:
            return explicit
        symbol = self._extract_symbol(text)
        return symbol or self.memory_name

    def add_situations(self, situations_and_advice):
        if not situations_and_advice:
            return

        try:
            from core.memory.service import get_memory_service

            svc = get_memory_service()
            for situation, recommendation in situations_and_advice:
                payload = (
                    f"Legacy situation:\n{situation}\n\n"
                    f"Recommendation:\n{recommendation}"
                )
                result = _run_async_sync(
                    svc.store(
                        [{"role": "user", "content": payload}],
                        user_id=self._resolve_user_id(),
                        agent_id=self.agent_id,
                        session_id=self._resolve_session_id(situation),
                        scope="agent_experience",
                        metadata=self._build_metadata(str(situation or ""), str(recommendation or "")),
                        infer=False,
                    )
                )
                if not result.success:
                    raise RuntimeError(result.error or "mem0 store failed")
            logger.info("✅ [MemoryProvider] mem0 compat Write successfully memory=%s agent_id=%s", self.memory_name, self.agent_id)
            return
        except Exception as exc:
            logger.warning("⚠️ [MemoryProvider] mem0 compat Write failed memory=%s: %s", self.memory_name, exc)
            return

    def get_memories(self, current_situation, n_matches=1):
        try:
            from core.memory.service import get_memory_service

            svc = get_memory_service()
            memories = []
            seen_memory_ids = set()
            metadata_filters = self._build_metadata_filters(str(current_situation or ""))

            for agent_id in self.agent_ids:
                recalled = _run_async_sync(
                    svc.recall(
                        query=str(current_situation or ""),
                        user_id=self._resolve_user_id(),
                        agent_id=agent_id,
                        scopes=["agent_experience"],
                        limit=n_matches,
                        metadata_filters=metadata_filters,
                    )
                )
                for item in recalled or []:
                    memory_id = getattr(item, "id", None)
                    if memory_id and memory_id in seen_memory_ids:
                        continue
                    if memory_id:
                        seen_memory_ids.add(memory_id)
                    memories.append(item)
                    if len(memories) >= n_matches:
                        break
                if len(memories) >= n_matches:
                    break

            if memories:
                logger.info(
                    "✅ [MemoryProvider] mem0 compat hit memory=%s recalled=%d agent_ids=%s",
                    self.memory_name,
                    len(memories),
                    self.agent_ids,
                )
                return [
                    {
                        "situation": item.metadata.get("legacy_situation") or item.memory,
                        "recommendation": item.metadata.get("legacy_recommendation") or item.memory,
                        "similarity": item.score,
                        "distance": max(0.0, 1.0 - float(item.score or 0.0)),
                    }
                    for item in memories
                ]
            logger.info(
                "📭 [MemoryProvider] mem0 compat miss memory=%s agent_ids=%s",
                self.memory_name,
                self.agent_ids,
            )
        except Exception as exc:
            logger.warning("⚠️ [MemoryProvider] mem0 compat Recall failed memory=%s: %s", self.memory_name, exc)
        return []


class MemoryProvider:
    """
    Memory provider
    
    Manage and create various types of Memory instances, supporting lazy loading.
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        memory_enabled: bool = True
    ):
        """
        Initialize the Memory provider
        
        Args:
            config: Configuration dictionary, including llm_provider, backend_url Wait
            memory_enabled: Whether to enable memory function
        """
        self.config = config or self._get_default_config()
        self.memory_enabled = memory_enabled
        self._memories: Dict[str, Any] = {}
        self._use_mem0_compat = self.config.get("memory_use_mem0_compat", True)
        
        if memory_enabled:
            logger.info("🧠 [MemoryProvider] Memory Feature is enabled")
        else:
            logger.info("⚠️ [MemoryProvider] Memory Feature disabled")
        if memory_enabled and not self._use_mem0_compat:
            logger.warning("⚠️ [MemoryProvider] The legacy-only memory path is currently explicitly used, and it is recommended to move back to the mem0 main path.")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        try:
            from tradingagents.default_config import DEFAULT_CONFIG
            return DEFAULT_CONFIG.copy()
        except ImportError:
            return {
                "llm_provider": "deepseek",
                "backend_url": "https://api.deepseek.com",
                "memory_enabled": True
            }
    
    def get_memory(self, memory_name: str) -> Optional[Any]:
        """
        Get the specified Memory instance
        
        Args:
            memory_name: Memory name, such as "bull_memory"
            
        Returns:
            memory instance or None
        """
        if not self.memory_enabled:
            return None
            
        if memory_name not in self._memories:
            self._memories[memory_name] = self._create_memory(memory_name)
        
        return self._memories[memory_name]
    
    def _create_memory(self, memory_name: str) -> Optional[Any]:
        """Create a Memory instance"""
        if not self.memory_enabled:
            return None
            
        try:
            if self._use_mem0_compat:
                memory = Mem0CompatMemory(memory_name, self.config)
            else:
                from tradingagents.agents.utils.memory import FinancialSituationMemory
                legacy_memory = FinancialSituationMemory(memory_name, self.config)
                memory = legacy_memory
            logger.debug(f"🧠 [MemoryProvider] Create Memory: {memory_name}")
            return memory
        except Exception as e:
            logger.warning(f"⚠️ [MemoryProvider] Failed to create Memory {memory_name}: {e}")
            return None
    
    def get_memory_config(self) -> Dict[str, Any]:
        """
        Get the Memory configuration of all Agents

        Returns:
            Dictionary, the keys are agent_id and memory_name, the value is the corresponding Memory instance
        """
        memory_config = {}

        for memory_name, agent_ids in MEMORY_AGENT_MAPPING.items():
            memory = self.get_memory(memory_name)
            # Use both memory_name and agent_id as key
            memory_config[memory_name] = memory
            for agent_id in agent_ids:
                memory_config[agent_id] = memory

        # Set default memory
        memory_config["default"] = self.get_memory("invest_judge_memory")

        return memory_config
    
    def get_memory_by_agent(self, agent_id: str) -> Optional[Any]:
        """
        Get the corresponding one based on Agent ID Memory
        
        Args:
            agent_id: Agent ID, Such as "bull_researcher"
            
        Returns:
            the corresponding Memory instance or None
        """
        for memory_name, agent_ids in MEMORY_AGENT_MAPPING.items():
            if agent_id in agent_ids:
                return self.get_memory(memory_name)
        
        # Return by default invest_judge_memory
        return self.get_memory("invest_judge_memory")
    
    def clear_memories(self):
        """Clear all Memory cache"""
        self._memories.clear()
        logger.debug("🧹 [MemoryProvider] Memory cache cleared")

