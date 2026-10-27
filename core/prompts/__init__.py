"""
Prompt word management module

Manage multilingual prompt word templates
"""

from .manager import PromptManager
from .template import PromptTemplate
from .loader import PromptLoader

__all__ = [
    "PromptManager",
    "PromptTemplate",
    "PromptLoader",
]

