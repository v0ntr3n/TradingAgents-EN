"""
Channel push configuration data model

Supported channel types:
- feishu     Feishu custom robot Webhook
- dingtalk   DingTalk custom robot Webhook
- wechatwork Enterprise WeChat custom robot Webhook
- email      Mail (reuse existing SMTP configuration)
"""
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ChannelType(str, Enum):
    """Channel type"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECHATWORK = "wechatwork"
    EMAIL = "email"


# Supported event types
EVENT_TYPES = [
    "analysis_complete",   # Analysis completed
    "alert",               # early warning
    "skill_gap",           # tool gap perception
    "system",              # System notification
]

CHANNEL_TYPE_NAMES = {
    ChannelType.FEISHU: "Feishu",
    ChannelType.DINGTALK: "DingTalk",
    ChannelType.WECHATWORK: "Enterprise WeChat",
    ChannelType.EMAIL: "Mail",
}


class ChannelConfig(BaseModel):
    """Channel configuration"""
    channel_id: str
    type: ChannelType
    name: str
    enabled: bool = True
    webhook_url: Optional[str] = None      # Webhook channel
    email_address: Optional[str] = None   # Email channel
    events: List[str] = Field(default_factory=lambda: ["analysis_complete", "alert"])
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ChannelConfigCreate(BaseModel):
    """Create channel configuration request"""
    type: ChannelType
    name: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    webhook_url: Optional[str] = None
    email_address: Optional[str] = None
    events: List[str] = Field(default_factory=lambda: ["analysis_complete", "alert"])


class ChannelConfigUpdate(BaseModel):
    """Update channel configuration request"""
    name: Optional[str] = None
    enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    email_address: Optional[str] = None
    events: Optional[List[str]] = None


class TestSendRequest(BaseModel):
    """Test push request"""
    title: str = "TradingAgents-CN Test notification"
    content: str = "This is a test message, if you receive this message, the channel is configured correctly."

