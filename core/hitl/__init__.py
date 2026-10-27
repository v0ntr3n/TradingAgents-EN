"""
Universal HITL (Human-in-the-Loop) module.

Provides management of pending operations across subsystems:
- Intelligent assistant key operation confirmation (item 4)
- Skill Bind only after review (item 6)

Core services:HITLCheckpointService
"""

from .checkpoint_store import (
    HITLCheckpointService,
    PendingOperation,
    get_hitl_service,
    COLLECTION_NAME,
)

__all__ = [
    "HITLCheckpointService",
    "PendingOperation",
    "get_hitl_service",
    "COLLECTION_NAME",
]

