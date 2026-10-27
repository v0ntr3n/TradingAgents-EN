"""
Skill system module

Based on Agent Skills open standards + Hybrid Skill system for extended fields.

Support:
1. Import of standard Agent Skills format (SKILL.md)
2. Extension fields support Function Calling (parameters, returns, implementation) 
3. Various execution protocols (python, http, mcp) 
4. Standard interface for third-party developers
"""

from .models import (
    SkillMetadata,
    SkillParameter,
    SkillReturns,
    ImplementationType,
    PythonImplementation,
    HttpImplementation,
    McpImplementation,
    SkillImplementation,
)
from .parser import SkillParser
from .converter import SkillConverter
from .executor import SkillExecutor

__all__ = [
    # Models
    "SkillMetadata",
    "SkillParameter",
    "SkillReturns",
    "ImplementationType",
    "PythonImplementation",
    "HttpImplementation",
    "McpImplementation",
    "SkillImplementation",
    # Parser
    "SkillParser",
    # Converter
    "SkillConverter",
    # Executor
    "SkillExecutor",
]

