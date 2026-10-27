"""
Tool call normalizer

Handle differences in tool call formats between different LLM providers
"""

import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional

from .models import LLMProvider, ToolCall, ToolResult

logger = logging.getLogger(__name__)


def normalize_ticker_for_engine(ticker: str) -> str:
    """
    Normalizes the ticker symbol passed in by LLM into the format expected by the analytics engine.
    The analysis engine and data sources (MongoDB, AKShare, etc.) use the unsuffixed format uniformly.

    - A shares: 002594.SZ / 600519.SH → 002594 / 600519 (6 bit pure number)
    - Hong Kong stocks: 0700.HK / 09988.HK → 0700 / 09988 (Remove .HK)
    - US stocks: AAPL → AAPL (unchanged)
    """
    if not ticker or not isinstance(ticker, str):
        return ticker
    s = ticker.strip().upper()
    # A Share: 6 digits + Exchange suffix → remove suffix
    if re.match(r'^\d{6}\.(SZ|SH|SS|XSHE|XSHG)$', s):
        return s.split('.')[0]
    # Hong Kong stocks: 4-5 digits.HK → remove suffix
    if re.match(r'^\d{4,5}\.HK$', s):
        return s.split('.')[0]
    return ticker


class ToolCallNormalizer:
    """
    Tool call normalizer
    
    Unified processing:
    1. Tool definition format conversion
    2. Tool call result conversion
    3. Tool execution and result packaging
    """
    
    @staticmethod
    def normalize_tool_definition(
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create standardized tool definitions from functions
        
        Args:
            func: Utility function
            name: Tool name (Use function name by default)
            description: Tool description (Use function docstrings by default)
            
        Returns:
            OpenAI Format tool definition
        """
        import inspect
        
        tool_name = name or func.__name__
        tool_desc = description or func.__doc__ or ""
        
        # Infer parameters from type annotations
        sig = inspect.signature(func)
        hints = func.__annotations__ if hasattr(func, '__annotations__') else {}
        
        properties = {}
        required = []
        
        for param_name, param in sig.parameters.items():
            if param_name in ('self', 'cls'):
                continue
            
            param_type = hints.get(param_name, str)
            json_type = ToolCallNormalizer._python_type_to_json(param_type)
            
            properties[param_name] = {
                "type": json_type,
                "description": f"parameters {param_name}"
            }
            
            if param.default == inspect.Parameter.empty:
                required.append(param_name)
        
        return {
            "type": "function",
            "function": {
                "name": tool_name,
                "description": tool_desc.strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
        }
    
    @staticmethod
    def _python_type_to_json(python_type) -> str:
        """Python Type conversion to JSON Schema type"""
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }
        return type_map.get(python_type, "string")

    @staticmethod
    def _merge_tool_arguments(arguments: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Compatible with history/exception tool calling format, automatically unpacking kwargs."""
        merged = {**(arguments or {}), **context}
        nested_kwargs = merged.get("kwargs")
        if isinstance(nested_kwargs, dict):
            normalized = {**nested_kwargs}
            for key, value in merged.items():
                if key != "kwargs":
                    normalized[key] = value
            return normalized
        return merged
    
    @staticmethod
    def execute_tool_call(
        tool_call: ToolCall,
        tools: Dict[str, Callable],
        **context
    ) -> ToolResult:
        """
        Execute tool call (synchronous version, only available for synchronous tool functions)

        Args:
            tool_call: Tool call object
            tools: Dictionary of available tools {name: callable}
            **context: Context parameters passed to the tool

        Returns:
            Tool execution results
        """
        import inspect

        if tool_call.name not in tools:
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Error: Tool not found '{tool_call.name}'",
                is_error=True
            )

        try:
            func = tools[tool_call.name]
            # Merge parameters
            kwargs = ToolCallNormalizer._merge_tool_arguments(tool_call.arguments, context)
            # Normalized ticker: The analysis engine uses the unsuffixed format (002594 instead of 002594.SZ)
            for key in ('ticker', 'symbol'):
                if key in kwargs and kwargs[key]:
                    kwargs[key] = normalize_ticker_for_engine(str(kwargs[key]))

            # If it is an asynchronous function, it will be executed in the new event loop (compatible with synchronous calling scenarios)
            if inspect.iscoroutinefunction(func):
                import asyncio
                result = asyncio.get_event_loop().run_until_complete(func(**kwargs))
            else:
                result = func(**kwargs)

            # Make sure the result is a string
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)

            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=result,
                is_error=False
            )
        except Exception as e:
            logger.exception("[ToolNormalizer] Tool %s synchronization execution exception: %s", tool_call.name, e)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Tool execution error: {str(e)}",
                is_error=True
            )

    @staticmethod
    def _get_tool_timeout(tool_name: str) -> int:
        """Returns the timeout in seconds based on timeout_tier in the tool registry"""
        try:
            from core.tools import get_tool_registry, TOOL_TIMEOUT_SECONDS
            from core.tools.config import ToolTimeoutTier
            meta = get_tool_registry().get(tool_name)
            if meta:
                tier = getattr(meta, "timeout_tier", ToolTimeoutTier.MEDIUM)
                return TOOL_TIMEOUT_SECONDS.get(tier, TOOL_TIMEOUT_SECONDS[ToolTimeoutTier.MEDIUM])
        except Exception:
            pass
        return 45  # Default medium

    @staticmethod
    async def aexecute_tool_call(
        tool_call: ToolCall,
        tools: Dict[str, Callable],
        **context
    ) -> ToolResult:
        """
        Executes tool calls asynchronously, correctly handles asynchronous and synchronous tool functions, and protects against layered timeouts.

        - Asynchronous tools: direct await calls
        - Synchronization tools: run in a thread pool to avoid blocking the event loop
        - Timeout protection: according to tool timeout_tier(light=15s, medium=45s, heavy=180s) 

        Args:
            tool_call: Tool call object
            tools: Dictionary of available tools {name: callable}
            **context: Context parameters passed to the tool

        Returns:
            Tool execution results
        """
        import asyncio
        import inspect

        if tool_call.name not in tools:
            # Reporting capability gaps: LLM calls a tool that does not exist
            try:
                from core.tools.external.skill_gap_detector import SkillGapDetector
                SkillGapDetector.report_gap(
                    gap_type="tool_not_found",
                    tool_name=tool_call.name,
                    agent_id="intelligent_assistant",
                    error="Tool does not exist in the current registry",
                    context={
                        "tool_call_args": tool_call.arguments,
                        "available_tools_sample": list(tools.keys())[:20],
                    },
                )
            except Exception:
                pass

            # Record to execution log
            try:
                from core.tools.execution_logger import get_tool_execution_logger
                get_tool_execution_logger().log(
                    tool_id=tool_call.name,
                    agent_id="intelligent_assistant",
                    tool_args=tool_call.arguments,
                    result=None,
                    success=False,
                    execution_time_ms=0,
                    error="tool_not_found",
                )
            except Exception:
                pass

            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Error: Tool not found '{tool_call.name}'",
                is_error=True
            )

        timeout_seconds = ToolCallNormalizer._get_tool_timeout(tool_call.name)
        import time as _time
        _exec_start = _time.perf_counter()

        def _log_exec(success: bool, result_str=None, error_str=None):
            try:
                from core.tools.execution_logger import get_tool_execution_logger
                get_tool_execution_logger().log(
                    tool_id=tool_call.name,
                    agent_id="intelligent_assistant",
                    tool_args=tool_call.arguments,
                    result=result_str,
                    success=success,
                    execution_time_ms=int((_time.perf_counter() - _exec_start) * 1000),
                    error=error_str,
                )
            except Exception:
                pass

        try:
            func = tools[tool_call.name]
            kwargs = ToolCallNormalizer._merge_tool_arguments(tool_call.arguments, context)
            for key in ('ticker', 'symbol'):
                if key in kwargs and kwargs[key]:
                    kwargs[key] = normalize_ticker_for_engine(str(kwargs[key]))

            if inspect.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(**kwargs), timeout=timeout_seconds)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, **kwargs),
                    timeout=timeout_seconds,
                )

            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)

            _log_exec(success=True, result_str=result)
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=result,
                is_error=False
            )
        except asyncio.TimeoutError:
            logger.warning(
                "[ToolNormalizer] Tool %s execution timed out (%ds) and was interrupted",
                tool_call.name, timeout_seconds,
            )
            _log_exec(success=False, error_str=f"timeout {timeout_seconds}s")
            # Report execution timeout as a capability gap (indirectly indicating that the tool efficiency is not up to expectations)
            try:
                from core.tools.external.skill_gap_detector import SkillGapDetector
                SkillGapDetector.report_gap(
                    gap_type="tool_execution_error",
                    tool_name=tool_call.name,
                    agent_id="intelligent_assistant",
                    error=f"Tool execution timeout ({timeout_seconds}seconds)",
                    context={"tool_call_args": tool_call.arguments},
                )
            except Exception:
                pass
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Tool execution timeout (exceeded {timeout_seconds} seconds limit), try simplifying the parameters or try again later.",
                is_error=True
            )
        except Exception as e:
            logger.exception("[ToolNormalizer] Tool %s asynchronous execution exception: %s", tool_call.name, e)
            _log_exec(success=False, error_str=str(e))
            # Report execution errors as capability gaps
            try:
                from core.tools.external.skill_gap_detector import SkillGapDetector
                SkillGapDetector.report_gap(
                    gap_type="tool_execution_error",
                    tool_name=tool_call.name,
                    agent_id="intelligent_assistant",
                    error=str(e),
                    context={"tool_call_args": tool_call.arguments},
                )
            except Exception:
                pass
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_call.name,
                content=f"Tool execution error: {str(e)}",
                is_error=True
            )

    @staticmethod
    def tool_result_to_message(
        result: ToolResult,
        provider: LLMProvider
    ) -> Dict[str, Any]:
        """
        Convert tool results to message format
        
        Args:
            result: Tool execution results
            provider: LLM provider
            
        Returns:
            Provider-specific message format
        """
        if provider == LLMProvider.GOOGLE:
            return {
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": result.name,
                        "response": {"result": result.content}
                    }
                }]
            }
        else:
            # OpenAI Compatible formats
            return {
                "role": "tool",
                "tool_call_id": result.tool_call_id,
                "name": result.name,
                "content": result.content
            }

