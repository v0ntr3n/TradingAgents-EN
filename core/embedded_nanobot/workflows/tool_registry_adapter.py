"""Adapter: Let core.tools.registry provide the interface to Nanobot ToolRegistry.

LangGraph Nodes (agent_builder_nodes.py) requires tool_registry.get(name).to_schema()
and tool_registry.execute(name, params) interface. This adapter wraps core.tools.registry to provide the same interface.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

logger = logging.getLogger(__name__)


class _ToolMetadataWrapper:
    """Wrapper ToolMetadata, provides to_schema() and func attributes."""

    def __init__(self, metadata: Any, executor: Any = None):
        self._metadata = metadata
        self._executor = executor  # StandardToolRegistryAdapter Reference, used to execute the tool
        self.name = metadata.id

    # func Properties used by _run_node_llm_fc of agent_builder_nodes.py,
    # It looks for the func/execute/run/handler attribute on the wrapper to execute the tool.
    @property
    def func(self):
        if not self._executor:
            return None
        # Returns an async callable with signature(**kwargs) -> str
        async def _execute(**kwargs):
            return await self._executor.execute(self.name, kwargs)
        return _execute

    def to_schema(self) -> dict[str, Any]:
        raw_params = self._metadata.parameters
        # Must be converted into the JSON Schema object format required by OpenAI Function Calling:
        # {"type": "object", "properties": {...}, "required": [...]}
        if raw_params:
            properties = {}
            required = []
            for p in raw_params:
                if hasattr(p, "model_dump"):
                    d = p.model_dump(mode="json", exclude_none=True)
                elif hasattr(p, "dict"):
                    d = p.dict()
                elif isinstance(p, dict):
                    d = p
                else:
                    continue
                name = d.pop("name", None)
                if not name:
                    continue
                if d.pop("required", False):
                    required.append(name)
                properties[name] = d
            params_payload = {"type": "object", "properties": properties}
            if required:
                params_payload["required"] = required
            # Also retains the original array format for older code that may directly iterate over the parameters
            params_payload["__raw_params__"] = [
                dict(name=name, **prop) for name, prop in properties.items()
            ]
        else:
            params_payload = {"type": "object", "properties": {}}
        return {
            "name": self._metadata.id,
            "description": self._metadata.description or self._metadata.name,
            "parameters": params_payload,
        }


class StandardToolRegistryAdapter:
    """Adapter:core.tools.registry → ToolRegistry interface."""

    def __init__(self):
        from core.tools import get_tool_registry
        self._registry = get_tool_registry()
        self._metadata_map: dict[str, Any] = {}
        for meta in self._registry.list_all():
            if meta.fc_enabled:
                self._metadata_map[meta.id] = meta

    def get(self, name: str) -> _ToolMetadataWrapper | None:
        meta = self._metadata_map.get(name)
        return _ToolMetadataWrapper(meta, executor=self) if meta else None

    def has(self, name: str) -> bool:
        return name in self._metadata_map

    async def execute(self, name: str, params: dict[str, Any]) -> str:
        func = self._registry.get_function(name)
        if not func:
            available = ", ".join(self._metadata_map.keys())
            return f"Error: Tool '{name}' not found. Available: {available}"
        try:
            # core.tools.registry Registered functions may be synchronous (def) or asynchronous (async def),
            # Call it first, if it returns coroutine and then await, it is compatible with both situations.
            result = func(**params)
            if inspect.isawaitable(result):
                result = await result
            result_str = str(result) if not isinstance(result, str) else result
            logger.info("[ToolAdapter][Success] tool=%s result_chars=%d", name, len(result_str))
            return result_str
        except Exception as exc:
            logger.exception("[ToolAdapter][Exception] tool=%s params=%s", name, params)
            return f"Error executing {name}: {exc}"

    @property
    def tool_names(self) -> list[str]:
        return list(self._metadata_map.keys())

    def get_definitions(self) -> list[dict[str, Any]]:
        return [self.get(name).to_schema() for name in self._metadata_map]  # type: ignore[union-attr]
