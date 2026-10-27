"""
Skill ↔ Function Calling converter

Convert SkillMetadata to:
1. OpenAI Function Calling tool definition format
2. ToolMetadata (Compatible with existing ToolRegistry)
3. Convert from existing ToolMetadata to SkillMetadata
"""

import logging
from typing import Any, Dict, List, Optional

from .models import (
    ImplementationType,
    PythonImplementation,
    SkillMetadata,
    SkillParameter,
    SkillReturns,
)

logger = logging.getLogger(__name__)


# JSON type mapping
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


class SkillConverter:
    """Skill converter"""

    @staticmethod
    def to_openai_tool(skill: SkillMetadata) -> Dict[str, Any]:
        """
        Convert SkillMetadata to OpenAI Function Calling tool definition

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
        # Build Description: Merge description + when_to_use
        description = skill.description
        if skill.when_to_use:
            description += f"\n\n When to use: {skill.when_to_use}"

        # build parameters JSON Schema
        properties = {}
        required = []

        for param in skill.parameters:
            json_type = _TYPE_MAP.get(param.type.lower(), "string")
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

        # Tool name: Convert hyphens to underscores (required by OpenAI)
        tool_name = skill.name.replace("-", "_")

        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @staticmethod
    def to_openai_tools(skills: List[SkillMetadata]) -> List[Dict[str, Any]]:
        """Batch convert SkillMetadata to OpenAI tool definition list"""
        tools = []
        for skill in skills:
            if skill.enabled and skill.fc_enabled and skill.parameters:
                tools.append(SkillConverter.to_openai_tool(skill))
        return tools

    @staticmethod
    def to_tool_metadata(skill: SkillMetadata) -> "ToolMetadata":
        """
        Convert SkillMetadata to ToolMetadata (compatible with existing ToolRegistry)

        Delayed import avoids circular dependencies
        """
        from core.tools.config import ToolMetadata, ToolParameter

        parameters = [
            ToolParameter(
                name=p.name,
                type=p.type,
                description=p.description,
                required=p.required,
                default=p.default,
                enum=p.enum,
            )
            for p in skill.parameters
        ]

        tool_id = skill.name.replace("-", "_")

        return ToolMetadata(
            id=tool_id,
            name=skill.description[:50] if len(skill.description) > 50 else skill.description,
            description=skill.description,
            category=skill.category,
            parameters=parameters,
            data_source=skill.skill_type,
            is_online=True,
            timeout=30,
            icon=skill.icon,
            color=skill.color,
        )

    @staticmethod
    def from_tool_metadata(
        tool_metadata: "ToolMetadata",
        tool_id: Optional[str] = None,
    ) -> SkillMetadata:
        """
        Convert from existing ToolMetadata to SkillMetadata

        Used to upgrade existing built-in tools to Skill
        """
        from core.tools.config import ToolMetadata as TM

        parameters = [
            SkillParameter(
                name=p.name,
                type=p.type,
                description=p.description,
                required=p.required,
                default=p.default,
                enum=p.enum,
            )
            for p in tool_metadata.parameters
        ]

        actual_id = tool_id or tool_metadata.id
        skill_name = actual_id.replace("_", "-")

        return SkillMetadata(
            name=skill_name,
            description=tool_metadata.description,
            category=tool_metadata.category,
            parameters=parameters,
            icon=tool_metadata.icon,
            color=tool_metadata.color,
            implementation=PythonImplementation(
                type=ImplementationType.PYTHON,
                module="",  # Built-in tools do not require specific modules
                function=actual_id,
            ),
            is_builtin=True,
            fc_enabled=True,
            enabled=True,
        )

