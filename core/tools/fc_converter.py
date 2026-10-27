"""
ToolMetadata → OpenAI Function Calling format converter

Convert ToolMetadata into OpenAI compatible tool definitions for use by LLM Function Calling.
Align with SkillConverter to ensure tool descriptions are consistent with Skill metadata.
"""

import re
from typing import Any, Dict, List

from .config import ToolMetadata, ToolParameter

# JSON Schema type mapping
_TYPE_MAP = {
    "string": "string",
    "str": "string",
    "integer": "integer",
    "int": "integer",
    "number": "number",
    "float": "number",
    "boolean": "boolean",
    "bool": "boolean",
    "array": "array",
    "list": "array",
    "object": "object",
    "dict": "object",
}

# OpenAI Legal character rules for tool names:^[a-zA-Z0-9_-]+$
_OPENAI_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_function_name(name: str) -> str:
    """Clean any string into a string that conforms to the OpenAI tool name specification

    - Replace illegal characters (Chinese, spaces, brackets, dots, etc.) with underscores
    - Merge redundant consecutive underscores
    - Remove leading and trailing underscores
    - If it is empty after cleaning, return 'tool'
    """
    if not name:
        return "tool"
    cleaned = _OPENAI_NAME_PATTERN.sub("_", str(name))
    cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
    return cleaned or "tool"


def tool_metadata_to_openai(tool: ToolMetadata) -> Dict[str, Any]:
    """
    Convert ToolMetadata to OpenAI Function Calling tool definition format

    Args:
        tool: Tool metadata

    Returns:
        OpenAI Format tool definition:
        {
            "type": "function",
            "function": {
                "name": "...",
                "description": "...",
                "parameters": { ... }
            }
        }
    """
    # Build Description: Merge description + when_to_use (Aligned with SkillConverter)
    description = tool.description
    if tool.when_to_use:
        description += f"\n\n何时使用: {tool.when_to_use}"
    if tool.when_not_to_use:
        description += f"\n\n不宜使用: {tool.when_not_to_use}"

    # build parameters JSON Schema
    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param in tool.parameters:
        json_type = _TYPE_MAP.get(param.type.lower() if param.type else "string", "string")
        prop: Dict[str, Any] = {
            "type": json_type,
            "description": param.description,
        }
        if param.enum:
            prop["enum"] = param.enum
        if param.default is not None:
            prop["default"] = param.default
        properties[param.name] = prop

        if param.required:
            required.append(param.name)

    return {
        "type": "function",
        "function": {
            "name": sanitize_function_name(tool.id),  # OpenAI request ^[a-zA-Z0-9_-]+$
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def tool_metadata_list_to_openai(tools: List[ToolMetadata]) -> List[Dict[str, Any]]:
    """
    Batch convert ToolMetadata to OpenAI tool definition list

    Convert only fc_enabled=True Tools (parameterless tools are also supported)
    """
    result = []
    for tool in tools:
        if tool.fc_enabled:
            result.append(tool_metadata_to_openai(tool))
    return result
