"""
Memory module v2.0 / v3.0

v2.0: Multi-backend vector memory system (Qdrant/ChromaDB)— Used for Agent historical experience
v3.0: mem0 unified memory layer — Intelligent memory storage and recall across subsystems
"""

from .memory_manager import MemoryManager, AgentMemory, Mem0AgentMemory, VectorStoreManager
from .chromadb_config import get_optimal_chromadb_client, is_windows_11

# v3.0 unified memory layer
from .models import MemoryItem, MemoryScope, StoreResult
from .service import MemoryService, get_memory_service

# Backward compatibility: ChromaDBManager has been renamed to VectorStoreManager
ChromaDBManager = VectorStoreManager

__all__ = [
    # v2.0
    'MemoryManager',
    'AgentMemory',
    'Mem0AgentMemory',
    'VectorStoreManager',
    'ChromaDBManager',
    'get_optimal_chromadb_client',
    'is_windows_11',
    # v3.0 mem0 unified memory layer
    'MemoryService',
    'get_memory_service',
    'MemoryItem',
    'MemoryScope',
    'StoreResult',
]

