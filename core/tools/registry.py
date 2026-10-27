"""
Tool registry

Manage metadata and discovery for all available tools
"""

import logging
import threading
from typing import Dict, List, Optional, Callable, Any, Tuple, Type

from .config import ToolMetadata, ToolCategory, BUILTIN_TOOLS

logger = logging.getLogger(__name__)


_PARAMETER_TYPE_MAP: Dict[str, Tuple[type, Any]] = {
    "string": (str, ""),
    "number": (float, 0.0),
    "integer": (int, 0),
    "boolean": (bool, False),
    "array": (list, []),
    "object": (dict, {}),
}


class ToolRegistry:
    """
    Tool registry (singleton mode)
    
    Usage:
        registry = ToolRegistry()
        
        # Get all the tools
        all_tools = registry.list_all()
        
        # Get category-specific tools
        market_tools = registry.get_by_category("market")
        
        # Get the tools available for an Agent
        tools = registry.get_tools_for_agent("market_analyst")
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(ToolRegistry, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._tools: Dict[str, ToolMetadata] = {}
            self._functions: Dict[str, Callable] = {}  # Store actual function implementation
            self._load_builtin_tools()
            # ⚠️ First mark it as initialized and then load the tool module.
            # Otherwise load_all() When importing a module, the module's @register_tool The decorator will trigger
            # ToolRegistry() → __init__ → _initialized Still False → re-enter
            # load_all() → Unbounded recursion (RecursionError).
            self._initialized = True
            self._load_tool_implementations()  # Automatic loading tool implementation

    def _load_builtin_tools(self) -> None:
        """加载内置工具元数据"""
        for tool_id, metadata in BUILTIN_TOOLS.items():
            self._tools[tool_id] = metadata

    def _load_tool_implementations(self) -> None:
        """加载工具函数实现"""
        try:
            from .loader import ToolLoader
            loader = ToolLoader()
            count = loader.load_all()
            logger.info(f"✅ 自动加载了 {count} 个工具模块")
        except Exception as e:
            logger.warning(f"⚠️ Failed to automatically load tool module: {e}")
    
    def register(self, metadata: ToolMetadata, override: bool = False) -> None:
        """注册工具"""
        if metadata.id in self._tools and not override:
            raise ValueError(f"工具 '{metadata.id}' 已注册，使用 override=True 覆盖")
        self._tools[metadata.id] = metadata
    
    def unregister(self, tool_id: str) -> None:
        """注销工具"""
        self._tools.pop(tool_id, None)
        self._functions.pop(tool_id, None)
    
    def get(self, tool_id: str) -> Optional[ToolMetadata]:
        """获取工具元数据"""
        return self._tools.get(tool_id)

    def has_tool(self, tool_id: str) -> bool:
        """检查工具是否已注册"""
        return tool_id in self._tools

    def get_tool(self, tool_id: str) -> Optional[ToolMetadata]:
        """Get tool metadata (alias method)"""
        return self.get(tool_id)

    def get_all_tools(self) -> List[ToolMetadata]:
        """获取所有工具（别名方法）"""
        return self.list_all()

    def list_all(self) -> List[ToolMetadata]:
        """列出所有工具"""
        return list(self._tools.values())
    
    def get_by_category(self, category: str) -> List[ToolMetadata]:
        """按类别获取工具"""
        return [t for t in self._tools.values() if t.category == category]
    
    def get_by_ids(self, tool_ids: List[str]) -> List[ToolMetadata]:
        """根据 ID 列表获取工具"""
        return [self._tools[tid] for tid in tool_ids if tid in self._tools]
    
    def get_online_tools(self) -> List[ToolMetadata]:
        """获取所有在线工具"""
        return [t for t in self._tools.values() if t.is_online]
    
    def get_offline_tools(self) -> List[ToolMetadata]:
        """获取所有离线工具"""
        return [t for t in self._tools.values() if not t.is_online]

    # ==================== Function registration (new) ====================

    def register_function(
        self,
        tool_id: str,
        func: Callable,
        name: str,
        category: str,
        description: str = "",
        is_online: bool = True,
        is_legacy: bool = False,
        override: bool = False,
        parameters: Optional[List] = None,
        timeout_tier: str = "",
        **kwargs
    ) -> None:
        """
        Register a function as a tool

        Args:
            tool_id: Tool only ID
            func: Actual function implementation
            name: Tool display name
            category: Tool classification
            description: Tool description
            is_online: Do you need to be online?
            is_legacy: Whether to adapt to old tools
            override: Whether to overwrite existing tools
            parameters: List of parameter definitions (optional, overrides parameters in metadata if provided)
            timeout_tier: Timeout tiering light/medium/heavy
        """
        # Defensive: tool_id must comply with the OpenAI tool name specification (^[a-zA-Z0-9_-]+$) 
        from .fc_converter import sanitize_function_name
        sanitized = sanitize_function_name(tool_id)
        if sanitized != tool_id:
            logger.warning(f"⚠️ tool_id '{tool_id}' Contains illegal characters and has been normalized to '{sanitized}'")
            tool_id = sanitized

        if tool_id in self._tools:
            if tool_id not in self._functions:
                self._functions[tool_id] = func
                if parameters is not None:
                    self._tools[tool_id].parameters = parameters
                if timeout_tier:
                    self._tools[tool_id].timeout_tier = timeout_tier
                metadata_fields = getattr(ToolMetadata, "model_fields", {})
                for key, value in kwargs.items():
                    if key in metadata_fields:
                        setattr(self._tools[tool_id], key, value)
                logger.debug(f"Add function implementation for registered tools: {tool_id}")
                return
            elif not override:
                logger.warning(f"工具 '{tool_id}' 已注册，跳过")
                return

        from .config import ToolTimeoutTier
        effective_tier = timeout_tier or ToolTimeoutTier.MEDIUM

        metadata_fields = getattr(ToolMetadata, "model_fields", {})
        metadata_payload = {
            "id": tool_id,
            "name": name,
            "description": description,
            "category": category,
            "is_online": is_online,
            "parameters": parameters or [],
            "timeout_tier": effective_tier,
        }
        for key, value in kwargs.items():
            if key in metadata_fields:
                metadata_payload[key] = value

        metadata = ToolMetadata(
            **metadata_payload,
        )

        self._tools[tool_id] = metadata
        self._functions[tool_id] = func

        logger.debug(f"注册工具函数: {tool_id} (legacy={is_legacy}, tier={effective_tier})")

    def get_function(self, tool_id: str) -> Optional[Callable]:
        """获取工具的函数实现"""
        return self._functions.get(tool_id)

    def _build_langchain_args_schema(self, metadata: ToolMetadata) -> Optional[Type]:
        """Build LangChain/Pydantic parametric models based on tool metadata."""
        if not metadata.parameters:
            return None

        from pydantic import Field, create_model

        field_definitions = {}
        for parameter in metadata.parameters:
            python_type, fallback_default = _PARAMETER_TYPE_MAP.get(parameter.type, (Any, None))
            if parameter.required:
                default_value = ...
            else:
                default_value = parameter.default if parameter.default is not None else fallback_default

            field_definitions[parameter.name] = (
                python_type,
                Field(default_value, description=parameter.description),
            )

        model_name = f"{metadata.id.title().replace('_', '')}Args"
        return create_model(model_name, **field_definitions)

    def get_langchain_tool(self, tool_id: str):
        """
        Tools for obtaining LangChain format

        Returns:
            LangChain Tool Object, returned if the tool is not registered or has no function implementation None
        """
        if tool_id not in self._tools:
            return None

        func = self._functions.get(tool_id)
        if func is None:
            return None

        # If it is already LangChain tool, return directly
        if hasattr(func, 'invoke') or hasattr(func, 'run'):
            return func

        # 🔥 Check whether the function is an asynchronous function, if so, it will be automatically packaged as a synchronous function
        import asyncio
        import inspect
        import functools

        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop is not None and loop.is_running():
                    import concurrent.futures
                    future = asyncio.run_coroutine_threadsafe(func(*args, **kwargs), loop)
                    return future.result(timeout=120)
                return asyncio.run(func(*args, **kwargs))

            func = _sync_wrapper
            logger.info(
                f"✅ 工具 {tool_id} 的异步函数已自动包装为同步函数，LangChain 可正常调用。"
            )
        
        # Otherwise the package is LangChain tool
        from langchain_core.tools import StructuredTool

        metadata = self._tools[tool_id]

        args_schema = None
        if metadata.source == "generated" and metadata.parameters:
            args_schema = self._build_langchain_args_schema(metadata)

        # Use StructuredTool.from_function to create tools
        # This allows you to explicitly specify name, description, and args_schema
        lc_tool = StructuredTool.from_function(
            func=func,
            name=tool_id,
            description=metadata.description or func.__doc__ or "No description available",
            args_schema=args_schema,
        )

        return lc_tool

    def get_langchain_tools(self, tool_ids: List[str]) -> List:
        """Tool for obtaining LangChain format in batches"""
        tools = []
        for tool_id in tool_ids:
            tool = self.get_langchain_tool(tool_id)
            if tool:
                tools.append(tool)
        return tools

    def register_external_skill(
        self,
        tool_id: str,
        func: Callable,
        display_name: str,
        description: str,
        category: str = "external",
        parameters: Optional[List] = None,
        **metadata_kwargs: Any,
    ) -> None:
        """
        Register AI-generated external skills to the tool registry.

        The generated Skill is sandboxed and registered as a tool that can be called by the Agent.
        """
        self.register_function(
            tool_id=tool_id,
            func=func,
            name=display_name,
            category=category,
            description=description,
            is_online=True,
            override=True,
            parameters=parameters,
            **metadata_kwargs,
        )
        if tool_id in self._tools:
            self._tools[tool_id].source = "generated"
        logger.info(f"注册外部 Skill: {tool_id}")

    def get_external_skills(self) -> List:
        """Get all AI generated external Skill"""
        return [t for t in self._tools.values() if getattr(t, 'source', '') == 'generated']


# Global registry instance
_global_registry: Optional[ToolRegistry] = None


def get_tool_registry() -> ToolRegistry:
    """获取全局工具注册表"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ToolRegistry()
    return _global_registry

