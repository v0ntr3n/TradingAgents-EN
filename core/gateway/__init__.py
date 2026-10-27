"""
Gateway module — IM Platform two-way access framework

Provides a unified message model, adapter base class, route distribution and session management,
Allow users of IM platforms such as Feishu/QQ/DingTalk to directly talk to the analysis assistant.

Core components:
- models.py       Unified Messaging Model (GatewayMessage/GatewayResponse)
- router.py       GatewayRouter Route distribution (select adapter, call assistant, reply)
- session.py      Multi-channel session management
- user_mapping.py IM User → System user mapping
- adapters/       Adapter implementation for each platform
"""

from core.gateway.models import (
    ChannelType,
    GatewayMessage,
    GatewayResponse,
    MessageType,
    ResponseType,
    UserMapping,
)
from core.gateway.adapters.base import BaseGatewayAdapter
from core.gateway.session import SessionManager
from core.gateway.user_mapping import UserMappingManager

__all__ = [
    "ChannelType",
    "GatewayMessage",
    "GatewayResponse",
    "MessageType",
    "ResponseType",
    "UserMapping",
    "BaseGatewayAdapter",
    "SessionManager",
    "UserMappingManager",
]

