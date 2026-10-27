"""
Skill data model

Mixed standards:
- Agent Skills Standard fields:name, description (ecologically compatible)
- Extension fields:parameters, returns, implementation (Function Calling support)
- Supports multiple execution protocols:python, http, mcp
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime


# =============================================================================
# Execution protocol definition
# =============================================================================

class ImplementationType(str, Enum):
    """Execution protocol type"""
    PYTHON = "python"   # Built-in Python functions
    HTTP = "http"       # external HTTP API
    MCP = "mcp"         # MCP Server


class PythonImplementation(BaseModel):
    """Python Function execution configuration
    
    Three execution methods are supported:
    1. module + function: Call existing Python functions within the project
    2. code: Directly execute a piece of Python code (sandbox execution), suitable for external import Skill
    3. skill_dir + script_path: Execute Python scripts in local Skill packages (ClawHub/OpenClaw)
    """
    type: ImplementationType = ImplementationType.PYTHON
    module: Optional[str] = Field(default=None, description="Python Module path, such as 'core.tools.implementations.market.stock_data'")
    function: Optional[str] = Field(default=None, description="Function name, such as 'get_stock_market_data_unified'")
    code: Optional[str] = Field(default=None, description="Directly executable Python code takes precedence over module/function")
    script_path: Optional[str] = Field(default=None, description="The script path in the local Skill package, such as 'scripts/fetch_data.py'")
    skill_dir: Optional[str] = Field(default=None, description="Local Skill Package Directory")
    timeout: int = Field(default=60, description="Script execution timeout (seconds)")
    is_async: bool = Field(default=False, description="Is it an asynchronous function?")


class HttpImplementation(BaseModel):
    """HTTP API Execute configuration"""
    type: ImplementationType = ImplementationType.HTTP
    url: str = Field(..., description="API URL, support {param} placeholder")
    method: str = Field(default="GET", description="HTTP method: GET, POST, PUT, DELETE")
    headers: Optional[Dict[str, str]] = Field(default=None, description="Request header")
    body_template: Optional[Dict[str, Any]] = Field(default=None, description="Request body template (POST/PUT)")
    auth: Optional[Dict[str, str]] = Field(default=None, description="Authentication configuration")
    response_mapping: Optional[Dict[str, str]] = Field(
        default=None,
        description="Response field mapping, such as {'result': 'data.items'}"
    )
    timeout: int = Field(default=30, description="Timeout (seconds)")


class McpImplementation(BaseModel):
    """MCP Server Execute configuration"""
    type: ImplementationType = ImplementationType.MCP
    server_url: str = Field(..., description="MCP Server URL (sse/streamable_http) or command path (stdio)")
    tool_name: str = Field(..., description="MCP Tool name")
    transport: str = Field(default="sse", description="transport protocol: stdio, sse, streamable_http")


# union type
SkillImplementation = Union[PythonImplementation, HttpImplementation, McpImplementation]


# =============================================================================
# Skill Parameters and return values
# =============================================================================

class SkillParameter(BaseModel):
    """Skill Parameter definition (compatible with Agent Skills + Function Calling) """
    name: str = Field(..., description="Parameter name")
    type: str = Field(default="string", description="Parameter type: string, integer, number, boolean, array, object")
    description: str = Field(default="", description="Parameter description")
    required: bool = Field(default=True, description="Is it required?")
    default: Optional[Any] = Field(default=None, description="Default value")
    enum: Optional[List[Any]] = Field(default=None, description="list of optional values")


class SkillReturns(BaseModel):
    """Skill Return value definition"""
    type: str = Field(default="string", description="Return type: string, object, array")
    description: str = Field(default="", description="Return value description")
    json_schema: Optional[Dict[str, Any]] = Field(default=None, alias="schema", description="JSON Schema Definition (optional)")

    class Config:
        populate_by_name = True


# =============================================================================
# Skill Metadata (Core Model)
# =============================================================================

class SkillMetadata(BaseModel):
    """
    Skill Metadata definition
    
    Mixed standards:
    - Agent Skills Standard fields (name + description + markdown body) 
    - extension field (parameters + returns + implementation) 
    """
    
    # ===== Agent Skills Standard fields =====
    name: str = Field(..., description="Skill Unique identifiers (lowercase, hyphen separated, e.g. 'get-stock-news') ")
    description: str = Field(..., description="Skill Description (a concise description of what to do and when to use it)")
    
    # ===== Agent Skills Optional standard fields =====
    allowed_tools: Optional[List[str]] = Field(default=None, description="Limit the list of tools that a skill can use")
    
    # ===== Extended metadata fields =====
    version: str = Field(default="1.0.0", description="version number")
    author: str = Field(default="", description="Author")
    category: str = Field(default="general", description="Classification")
    tags: List[str] = Field(default_factory=list, description="tag list")
    icon: str = Field(default="🔧", description="icon")
    color: str = Field(default="#95a5a6", description="color")
    
    # ===== Function Calling extension fields =====
    when_to_use: str = Field(default="", description="When to use this skill (detailed LLM call guidance)")
    parameters: List[SkillParameter] = Field(default_factory=list, description="Structured parameter definition")
    returns: Optional[SkillReturns] = Field(default=None, description="Return value definition")
    examples: List[str] = Field(default_factory=list, description="Usage example")
    
    # ===== Implementation =====
    implementation: Optional[SkillImplementation] = Field(
        default=None,
        description="Execute implementation configuration (python/http/mcp). None represents knowledge type Skill"
    )
    
    # ===== Markdown Command content =====
    instructions: str = Field(default="", description="SKILL.md The Markdown body section (natural language instructions)")
    
    # ===== Status and configuration =====
    enabled: bool = Field(default=True, description="Whether to enable")
    fc_enabled: bool = Field(default=True, description="Whether to enable Function Calling")
    is_builtin: bool = Field(default=False, description="Whether it is a built-in skill (converted from a code-registered tool)")
    source_file: Optional[str] = Field(default=None, description="Source file path (such as SKILL.md path)")
    
    # ===== Timestamp =====
    created_at: Optional[datetime] = Field(default=None, description="creation time")
    updated_at: Optional[datetime] = Field(default=None, description="Update time")
    
    @property
    def is_executable(self) -> bool:
        """Whether it is an executable Skill (with implementation and parameters)"""
        return self.implementation is not None
    
    @property
    def is_knowledge_only(self) -> bool:
        """Whether it is a pure knowledge-based Skill (only instructions, no implementation)"""
        return self.implementation is None
    
    @property
    def skill_type(self) -> str:
        """Skill Type description"""
        if self.is_knowledge_only:
            return "knowledge"
        if self.implementation:
            return self.implementation.type.value
        return "unknown"
    
    class Config:
        use_enum_values = True

