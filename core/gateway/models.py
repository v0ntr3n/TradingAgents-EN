"""
Gateway Unified Messaging Model

Define standard message formats between IM platforms and systems,
All adapters convert platform messages to GatewayMessage and system replies to GatewayResponse.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    """Supported IM platform types"""
    FEISHU = "feishu"
    QQ = "qq"
    DINGTALK = "dingtalk"
    WECHAT_WORK = "wechat_work"


class MessageType(str, Enum):
    """Message content type"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    COMMAND = "command"       # Slash commands like /bind, /help


class ResponseType(str, Enum):
    """Reply content type"""
    TEXT = "text"
    MARKDOWN = "markdown"
    CARD = "card"             # Feishu/DingTalk interactive cards


class GatewayMessage(BaseModel):
    """
    Unified inbound messaging — The adapter parses platform raw webhooks into this format

    All fields use platform-independent common naming.
    """
    channel_type: ChannelType
    channel_id: str = Field(..., description="Platform-side session ID (group chat ID/private chat ID)")
    user_identity: str = Field(..., description="Platform side user ID (open_id / QQ number)")
    message_type: MessageType = MessageType.TEXT
    content: str = Field(..., description="Message text (plain text or extracted text)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # Platform-specific extra data, populated by the adapter itself
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # If it is a group chat @Bot Scene, record whether the robot is at
    is_mention_bot: bool = False

    class Config:
        use_enum_values = True


class GatewayResponse(BaseModel):
    """
    Unified outbound reply — Gateway The route converts the assistant results into this format, and the adapter converts them into platform API calls
    """
    channel_type: str
    channel_id: str
    response_type: ResponseType = ResponseType.TEXT
    content: str = Field(default="", description="Text/Markdown content")
    card_template: Optional[Dict[str, Any]] = None
    attachments: List[Dict[str, Any]] = Field(default_factory=list)
    # Transparently transmit metadata (such as QQ's msg_id for passive replies)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


class UserMapping(BaseModel):
    """IM User ↔ System user binding record"""
    user_id: str = Field(..., description="System user_id (MongoDB ObjectId string)")
    platform: str = Field(..., description="Platform identifier, such as feishu / qq")
    platform_identity: str = Field(..., description="Unique identifier on the platform side")
    display_name: Optional[str] = None
    bound_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

