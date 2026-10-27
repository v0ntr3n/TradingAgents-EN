"""
Tool base classes and decorators

Provide tool-defined infrastructure
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, get_type_hints
from abc import ABC, abstractmethod
from langchain_core.tools import tool as langchain_tool

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    Tool base class
    
    All custom tools should inherit this class
    
    Example:
        class MyTool(BaseTool):
            id = "my_tool"
            name = "my tools"
            description = "Tool description"
            category = "custom"
            
            def execute(self, param1: str, param2: int) -> str:
                return f"result: {param1} - {param2}"
    """
    
    # Tool metadata (subclasses must define)
    id: str = ""
    name: str = ""
    description: str = ""
    category: str = "general"
    
    # Optional configuration
    is_online: bool = True
    timeout: int = 30
    rate_limit: Optional[int] = None
    
    @abstractmethod
    def execute(self, *args, **kwargs) -> Any:
        """
        Execute tool logic
        
        Subclasses must implement this method
        """
        pass
    
    def validate_params(self, **kwargs) -> bool:
        """
        Validation parameters (optional override)
        
        Returns:
            True if valid, False otherwise
        """
        return True
    
    def to_langchain_tool(self):
        """Convert to LangChain Tool"""
        @langchain_tool
        def wrapped_tool(*args, **kwargs):
            if not self.validate_params(**kwargs):
                raise ValueError(f"Invalid parameters for tool {self.id}")
            return self.execute(*args, **kwargs)
        
        wrapped_tool.name = self.id
        wrapped_tool.description = self.description
        return wrapped_tool


def register_tool(
    tool_id: str,
    name: str = "",
    description: str = "",
    category: str = "general",
    is_online: bool = True,
    auto_register: bool = True,
    parameters: Optional[List] = None,
    timeout_tier: str = "",
    data_source_handling: str = "",
    **kwargs
):
    """
    Tool registration decorator

    Usage 1: Decoration function
        @register_tool(
            tool_id="my_tool",
            name="my tools",
            category="custom",
            data_source_handling="self_contained"
        )
        def my_tool_func(param1: str) -> str:
            return f"Result: {param1}"

    Usage 2: Decoration
        @register_tool(
            tool_id="my_tool",
            name="my tools",
            category="custom",
            data_source_handling="local_only"
        )
        class MyTool(BaseTool):
            def execute(self, param1: str) -> str:
                return f"Result: {param1}"

    Args:
        tool_id: Tool only ID
        name: Tool display name
        description: Tool description
        category: Tool classification
        is_online: Do you need to be online?
        auto_register: Whether to automatically register to ToolRegistry
        data_source_handling: Data source processing method label (self_contained / local_only / partial), 
            If left blank, register_function will handle it based on the ToolMetadata default value.
    """
    def decorator(obj):
        # If it is a class
        if isinstance(obj, type):
            # Set metadata
            obj.id = tool_id
            obj.name = name or tool_id
            obj.description = description or obj.__doc__ or ""
            obj.category = category
            obj.is_online = is_online

            # Automatic registration
            if auto_register:
                extra_kwargs = dict(kwargs)
                if data_source_handling:
                    extra_kwargs["data_source_handling"] = data_source_handling
                _auto_register_class(obj, **extra_kwargs)

            return obj

        # If it is a function
        else:
            func = obj
            func._tool_id = tool_id
            func._tool_name = name or tool_id
            func._tool_description = description or func.__doc__ or ""
            func._tool_category = category
            func._tool_is_online = is_online
            func._tool_parameters = parameters
            func._tool_timeout_tier = timeout_tier

            if auto_register:
                extra_kwargs = dict(kwargs)
                if data_source_handling:
                    extra_kwargs["data_source_handling"] = data_source_handling
                _auto_register_function(func, parameters=parameters, timeout_tier=timeout_tier, **extra_kwargs)

            return func

    return decorator


def _auto_register_class(tool_class: type, **kwargs):
    """Automatically register tool classes to ToolRegistry"""
    try:
        from core.tools.registry import ToolRegistry
        
        registry = ToolRegistry()
        
        # Create instance
        instance = tool_class()
        
        # Register
        registry.register_function(
            tool_id=tool_class.id,
            func=instance.execute,
            name=tool_class.name,
            category=tool_class.category,
            description=tool_class.description,
            is_online=tool_class.is_online,
            **kwargs
        )
        
        logger.debug(f"自动注册工具类: {tool_class.id}")
    except Exception as e:
        logger.warning(f"自动注册工具类失败: {e}")


def _extract_parameters_from_signature(func: Callable) -> List:
    """
    Automatically extract parameter definition lists from function signatures.

    support:
    - Annotated[str, "Description"] → ToolParameter(name=..., type="string", description="Description")
    - Common type str, int, float, bool → automatic mapping
    - Default value → required=False, default=value
    """
    from core.tools.config import ToolParameter

    _type_map = {
        "str": "string",
        "int": "integer",
        "float": "number",
        "bool": "boolean",
        "list": "array",
        "dict": "object",
    }

    params = []
    # Get the original function (unwrap @tool and other decorators)
    raw_func = inspect.unwrap(func)
    sig = inspect.signature(raw_func)

    try:
        hints = get_type_hints(raw_func, include_extras=True)
    except Exception:
        hints = {}

    for name, param in sig.parameters.items():
        if name in ("self", "cls", "return"):
            continue

        hint = hints.get(name)
        description = ""
        base_type = "string"

        # Process Annotated[Type, "description"]
        if hint is not None and hasattr(hint, "__metadata__"):
            # Annotated type
            base = getattr(hint, "__origin__", hint)
            if hasattr(hint, "__args__") and hint.__args__:
                base = hint.__args__[0]
            base_type = _type_map.get(getattr(base, "__name__", str(base)), "string")
            # Extract description from metadata
            for meta in hint.__metadata__:
                if isinstance(meta, str):
                    description = meta
                    break
        elif hint is not None:
            type_name = getattr(hint, "__name__", str(hint))
            base_type = _type_map.get(type_name, "string")

        has_default = param.default is not inspect.Parameter.empty
        params.append(ToolParameter(
            name=name,
            type=base_type,
            description=description or f"参数 {name}",
            required=not has_default,
            default=param.default if has_default else None,
        ))

    return params


def _auto_register_function(func: Callable, parameters: Optional[List] = None, timeout_tier: str = "", **kwargs):
    """Automatically register tool functions to ToolRegistry"""
    try:
        from core.tools.registry import ToolRegistry

        registry = ToolRegistry()

        if parameters is None:
            extracted = _extract_parameters_from_signature(func)
            if extracted:
                parameters = extracted
                logger.debug(f"自动提取 {func._tool_id} 的 {len(extracted)} 个参数定义")

        registry.register_function(
            tool_id=func._tool_id,
            func=func,
            name=func._tool_name,
            category=func._tool_category,
            description=func._tool_description,
            is_online=func._tool_is_online,
            parameters=parameters,
            timeout_tier=timeout_tier,
            **kwargs
        )

        logger.info(f"✅ 自动注册工具函数: {func._tool_id}")
    except Exception as e:
        logger.error(f"❌ Automatic registration tool function failed ({getattr(func, '_tool_id', 'unknown')}): {e}", exc_info=True)

