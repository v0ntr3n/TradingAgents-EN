"""
Unified LLM client module

Provides a unified LLM calling interface and supports multiple backends:
- OpenAI Compatible API (DeepSeek, Tongyi Qianwen, Wisdom spectrum AI, Silicon based flow etc.)
- Google Generative AI
- Anthropic Claude

Main components:
- UnifiedLLMClient: Unified client portal
- LLMConfig: Configure model
- ToolCallNormalizer: Tool call standardization
"""

from .models import LLMConfig, LLMResponse, Message, ToolCall, ToolResult
from .unified_client import UnifiedLLMClient
from .tool_normalizer import ToolCallNormalizer
from .embedding_manager import EmbeddingManager

__all__ = [
    "UnifiedLLMClient",
    "LLMConfig",
    "LLMResponse",
    "Message",
    "ToolCall",
    "ToolResult",
    "ToolCallNormalizer",
    "EmbeddingManager",
]

