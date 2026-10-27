"""
Custom tool module

Supports dynamic creation and registration of HTTP-based custom tools
"""

import logging
import aiohttp
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from core.tools.registry import get_tool_registry
from core.tools.config import ToolMetadata, ToolParameter, ToolCategory

logger = logging.getLogger(__name__)

class HttpToolConfig(BaseModel):
    """HTTP工具配置"""
    url: str
    method: str = "GET"
    headers: Optional[Dict[str, str]] = None
    
class CustomToolDefinition(BaseModel):
    """自定义工具定义"""
    id: str
    name: str
    description: str
    category: str
    parameters: List[ToolParameter]
    implementation: HttpToolConfig
    is_online: bool = True
    timeout: int = 30

class GenericHttpTool:
    """通用HTTP工具执行器"""
    def __init__(self, definition: CustomToolDefinition):
        self.definition = definition
        
    async def execute(self, **kwargs):
        """执行HTTP请求"""
        config = self.definition.implementation
        
        # URL Parameter substitution
        url = config.url
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))
        
        # Prepare request parameters
        params = {}
        json_body = None
        
        # Exclude parameters already used in URL
        remaining_kwargs = {k: v for k, v in kwargs.items() if f"{{{k}}}" not in config.url}
        
        if config.method.upper() == "GET":
            params = remaining_kwargs
        elif config.method.upper() in ["POST", "PUT", "PATCH"]:
            json_body = remaining_kwargs
            
        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method=config.method,
                    url=url,
                    headers=config.headers,
                    params=params,
                    json=json_body,
                    timeout=self.definition.timeout
                ) as response:
                    # Try to parse the response
                    try:
                        result = await response.json()
                    except:
                        result = await response.text()
                        
                    if response.status >= 400:
                        raise Exception(f"HTTP {response.status}: {result}")
                    
                    return result
        except Exception as e:
            logger.error(f"工具 {self.definition.id} 执行失败: {e}")
            raise

async def register_custom_tool(definition: CustomToolDefinition):
    """Register custom tools into the global registry"""
    import asyncio
    import threading
    
    registry = get_tool_registry()
    
    # Create executor instance
    tool_instance = GenericHttpTool(definition)
    
    # 🔥 Create a synchronized wrapper function (LangChain tools require synchronized functions)
    def sync_wrapper(**kwargs):
        """
        Synchronous wrapper function for LangChain tool calls
        
        Note: This function will run asynchronous code internally
        """
        try:
            # Try to get the current event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # If the event loop is running (e.g. in an asynchronous context),
                # Need to run asynchronous code in a new thread
                result_container = {}
                exception_container = {}
                
                def run_async():
                    """在新线程中运行异步代码"""
                    try:
                        new_loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(new_loop)
                        result_container['value'] = new_loop.run_until_complete(
                            tool_instance.execute(**kwargs)
                        )
                        new_loop.close()
                    except Exception as e:
                        exception_container['value'] = e
                
                thread = threading.Thread(target=run_async, daemon=True)
                thread.start()
                thread.join(timeout=definition.timeout + 10)  # Timeout protection
                
                if thread.is_alive():
                    raise TimeoutError(f"工具执行超时（超过 {definition.timeout + 10} 秒）")
                
                if 'value' in exception_container:
                    raise exception_container['value']
                
                return result_container.get('value')
            else:
                # The event loop exists but is not running and can be used directly
                return loop.run_until_complete(tool_instance.execute(**kwargs))
        except RuntimeError:
            # No event loop, create new one (most common case)
            return asyncio.run(tool_instance.execute(**kwargs))
    
    # Set the wrapper's metadata so inspect can see it
    sync_wrapper.__name__ = definition.id
    sync_wrapper.__doc__ = definition.description
    
    # 🔥 Verify sync_wrapper is not a coroutine function
    import inspect
    if inspect.iscoroutinefunction(sync_wrapper):
        raise ValueError(
            f"工具 {definition.id} 的同步包装函数仍然是异步函数！"
            f"This causes the tool call to return the coroutine object."
        )
    
    logger.debug(f"🔍 验证工具 {definition.id} 的包装函数类型: {type(sync_wrapper)}")
    logger.debug(f"🔍 是否为协程函数: {inspect.iscoroutinefunction(sync_wrapper)}")
    
    registry.register_function(
        tool_id=definition.id,
        func=sync_wrapper,  # 🔥 Use synchronized wrapper functions
        name=definition.name,
        category=definition.category,
        description=definition.description,
        is_online=definition.is_online,
        override=True
    )
    
    # 🔥 Verify that the registered function is indeed synchronous
    registered_func = registry.get_function(definition.id)
    if registered_func and inspect.iscoroutinefunction(registered_func):
        logger.error(
            f"❌ 工具 {definition.id} 注册后仍然是异步函数！"
            f"Registered function type: {type(registered_func)}"
        )
    else:
        logger.debug(f"✅ 工具 {definition.id} 注册成功，函数类型: {type(registered_func)}")
    
    # Manually update parameter definitions
    # register_function Function signatures are parsed by default, but the wrapper is (**kwargs)
    # So we need to manually override the metadata parameters
    metadata = registry.get(definition.id)
    if metadata:
        metadata.parameters = definition.parameters
        metadata.data_source = "custom_http"
        metadata.icon = "🌐"  # Custom tool icon
        metadata.color = "#3498db"

    logger.info(f"✅ 自定义工具已注册: {definition.id}")
