"""
LLM provider adapter module

Each adapter is responsible for converting the unified interface into a provider-specific API format
"""

from .base import BaseAdapter
from .openai_compat import OpenAICompatAdapter

# Google Adapter is optional (requires google-generativeai package)
try:
    from .google import GoogleAdapter
    GOOGLE_AVAILABLE = True
except ImportError:
    GoogleAdapter = None
    GOOGLE_AVAILABLE = False

__all__ = [
    "BaseAdapter",
    "OpenAICompatAdapter",
]

if GOOGLE_AVAILABLE:
    __all__.append("GoogleAdapter")

