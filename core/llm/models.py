"""
LLM Related data model definitions
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class LLMProvider(str, Enum):
    """LLM Provider enumeration"""
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    DASHSCOPE = "dashscope"  # Tongyi Qianwen
    ZHIPU = "zhipu"          # Wisdom spectrum AI
    SILICONFLOW = "siliconflow"  # silicon based flow
    GOOGLE = "google"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    OPENROUTER = "openrouter"


class MessageRole(str, Enum):
    """message role"""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    """unified message format"""
    role: MessageRole
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    name: Optional[str] = None
    tool_calls: Optional[List["ToolCall"]] = None
    tool_call_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


class ToolCall(BaseModel):
    """Tool call definition"""
    id: str
    name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    
    @classmethod
    def from_openai_format(cls, tool_call: dict) -> "ToolCall":
        """Convert from OpenAI format"""
        import json
        return cls(
            id=tool_call.get("id", ""),
            name=tool_call.get("function", {}).get("name", ""),
            arguments=json.loads(tool_call.get("function", {}).get("arguments", "{}"))
        )
    
    @classmethod
    def from_google_format(cls, tool_call: dict) -> "ToolCall":
        """Convert from Google format"""
        return cls(
            id=tool_call.get("id", f"call_{hash(str(tool_call))}"),
            name=tool_call.get("name", ""),
            arguments=tool_call.get("args", {})
        )


class ToolResult(BaseModel):
    """Tool execution results"""
    tool_call_id: str
    name: str
    content: str
    is_error: bool = False


class LLMConfig(BaseModel):
    """LLM Configuration"""
    provider: LLMProvider
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.2  # Recommended values for stock analysis: 0.2-0.3 (quick analysis), 0.1-0.2 (in-depth analysis)
    max_tokens: Optional[int] = None
    timeout: int = 180
    retry_times: int = 3
    
    # Advanced configuration
    top_p: Optional[float] = None
    frequency_penalty: Optional[float] = None
    presence_penalty: Optional[float] = None
    
    # Tool call configuration
    tool_choice: Optional[str] = None  # "auto", "none", "required"
    parallel_tool_calls: bool = True
    
    class Config:
        use_enum_values = True
    
    @classmethod
    def from_env(cls, provider: LLMProvider) -> "LLMConfig":
        """Create configuration from environment variables"""
        import os
        import logging
        
        logger = logging.getLogger(__name__)
        
        config_map = {
            LLMProvider.OPENAI: {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            },
            LLMProvider.DEEPSEEK: {
                "api_key": os.getenv("DEEPSEEK_API_KEY"),
                "base_url": "https://api.deepseek.com",
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            },
            LLMProvider.DASHSCOPE: {
                "api_key": os.getenv("DASHSCOPE_API_KEY"),
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "model": os.getenv("DASHSCOPE_MODEL", "qwen-plus"),
            },
            LLMProvider.ZHIPU: {
                "api_key": os.getenv("ZHIPU_API_KEY"),
                "base_url": "https://open.bigmodel.cn/api/paas/v4",
                "model": os.getenv("ZHIPU_MODEL", "glm-4"),
            },
            LLMProvider.GOOGLE: {
                "api_key": os.getenv("GOOGLE_API_KEY"),
                "model": os.getenv("GOOGLE_MODEL", "gemini-2.0-flash"),
            },
            LLMProvider.ANTHROPIC: {
                "api_key": os.getenv("ANTHROPIC_API_KEY"),
                "model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            },
        }
        
        if provider not in config_map:
            raise ValueError(f"Unsupported provider: {provider}")
        
        config_data = config_map[provider]
        api_key = config_data.get("api_key")
        
        # 🔥 Check if the API key exists and log a warning if it does not exist
        if not api_key:
            env_key_map = {
                LLMProvider.OPENAI: "OPENAI_API_KEY",
                LLMProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
                LLMProvider.DASHSCOPE: "DASHSCOPE_API_KEY",
                LLMProvider.ZHIPU: "ZHIPU_API_KEY",
                LLMProvider.GOOGLE: "GOOGLE_API_KEY",
                LLMProvider.ANTHROPIC: "ANTHROPIC_API_KEY",
            }
            expected_env_key = env_key_map.get(provider, "API_KEY")
            logger.warning(
                f"⚠️ environment variables {expected_env_key} If not set, the LLM client may not function properly."
                f"Provider: {provider.value}, Model: {config_data.get('model', 'unknown')}"
            )
            logger.warning(
                f"💡 Please make sure you have called bridge_config_to_env() Or manually set environment variables {expected_env_key}"
            )
        
        return cls(provider=provider, **config_data)


class LLMResponse(BaseModel):
    """LLM response"""
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: List[ToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    
    # metadata
    model: Optional[str] = None
    provider: Optional[LLMProvider] = None
    usage: Optional[Dict[str, int]] = None
    
    @property
    def has_tool_calls(self) -> bool:
        """Is there a tool call"""
        return len(self.tool_calls) > 0
    
    def to_message(self) -> Message:
        """Convert to message format"""
        return Message(
            role=MessageRole.ASSISTANT,
            content=self.content,
            reasoning_content=self.reasoning_content,
            tool_calls=self.tool_calls if self.tool_calls else None
        )


# Update forward reference
Message.model_rebuild()

