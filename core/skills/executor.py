"""
Skill actuator

Responsible for performing the actual calls based on the Skill s implementation configuration:
- python: Call built-in Python functions
- http: call external HTTP API
- mcp: Call MCP Server (via MCPClientManager)
"""

import asyncio
import importlib
import json
import logging
import threading
from typing import Any, Callable, Dict, Optional

import aiohttp

from .models import (
    HttpImplementation,
    ImplementationType,
    McpImplementation,
    PythonImplementation,
    SkillImplementation,
    SkillMetadata,
)

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Skill actuator"""

    @staticmethod
    async def execute_async(skill: SkillMetadata, **kwargs) -> Any:
        """
        Asynchronous execution Skill
        
        Args:
            skill: Skill metadata
            **kwargs: Call parameters
            
        Returns:
            Execution result
        """
        if not skill.implementation:
            raise ValueError(f"Skill '{skill.name}' It is a knowledge-based Skill and does not support execution calls.")

        impl = skill.implementation
        impl_type = impl.type if isinstance(impl.type, str) else impl.type.value

        if impl_type == ImplementationType.PYTHON or impl_type == "python":
            return await SkillExecutor._execute_python(impl, **kwargs)
        elif impl_type == ImplementationType.HTTP or impl_type == "http":
            return await SkillExecutor._execute_http(impl, **kwargs)
        elif impl_type == ImplementationType.MCP or impl_type == "mcp":
            return await SkillExecutor._execute_mcp(impl, **kwargs)
        else:
            raise ValueError(f"Unsupported execution protocol: {impl_type}")

    @staticmethod
    def execute_sync(skill: SkillMetadata, **kwargs) -> Any:
        """
        Synchronous execution of Skill (providing synchronization interface for LangChain/Function Calling)
        """
        # Use threads uniformly + New event loop approach to avoid event loop nesting issues
        result_container: Dict[str, Any] = {}
        exception_container: Dict[str, Exception] = {}

        def run_async():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    result_container["value"] = new_loop.run_until_complete(
                        SkillExecutor.execute_async(skill, **kwargs)
                    )
                finally:
                    new_loop.close()
            except Exception as e:
                exception_container["value"] = e

        thread = threading.Thread(target=run_async, daemon=True)
        thread.start()
        thread.join(timeout=60)

        if thread.is_alive():
            raise TimeoutError("Skill Execution timeout (more than 60 seconds)")
        if "value" in exception_container:
            raise exception_container["value"]
        return result_container.get("value")

    # =========================================================================
    # Each protocol executor
    # =========================================================================

    @staticmethod
    async def _execute_python(impl: PythonImplementation, **kwargs) -> Any:
        """Execute Python functions, code, or local scripts"""
        # If code is provided, use sandbox execution
        if impl.code:
            return await SkillExecutor._execute_python_code(impl.code, **kwargs)

        # ClawHub/OpenClaw local script type Skill
        if impl.script_path and impl.skill_dir:
            from core.skills.script_executor import ScriptSkillExecutor
            result = await asyncio.to_thread(
                ScriptSkillExecutor.execute,
                skill_dir=impl.skill_dir,
                script_path=impl.script_path,
                args=kwargs,
                credentials={},
                timeout=impl.timeout,
            )
            if not result.get("success"):
                raise RuntimeError(result.get("error") or "Script execution failed")
            return result.get("result")

        # Find registered functions first from ToolRegistry
        from core.tools.registry import get_tool_registry

        registry = get_tool_registry()
        func_name = impl.function
        func = None

        # ⚠️ If module is provided, import the module directly to get the original function, do not use ToolRegistry
        #    Because ToolRegistry may store Skill wrapper wrapping functions,
        #    Will lead to infinite recursion:wrapper → execute_sync → _execute_python → wrapper → ...
        if impl.module:
            try:
                module = importlib.import_module(impl.module)
                func = getattr(module, func_name)
                # If the module layer function is @tool Decorated into StructuredTool, take out the original function
                from langchain_core.tools import StructuredTool
                if isinstance(func, StructuredTool):
                    func = func.func
            except (ImportError, AttributeError) as e:
                raise RuntimeError(
                    f"Unable to load Python function {impl.module}.{func_name}: {e}"
                )
        else:
            func = registry.get_function(func_name)

        if func is None:
            raise RuntimeError(f"Python function not found: {func_name}")

        # execute
        import inspect
        if inspect.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

    @staticmethod
    async def _execute_python_code(code: str, **kwargs) -> Any:
        """Execute Python code in a subprocess sandbox"""
        import subprocess
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(code)
            temp_path = f.name

        try:
            input_data = json.dumps(kwargs, ensure_ascii=False)
            proc = subprocess.run(
                ["python", temp_path],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).parent.parent.parent),
            )

            if proc.returncode != 0:
                raise RuntimeError(proc.stderr or "Code execution failed")

            stdout = proc.stdout.strip()
            if "__SANDBOX_OUTPUT_START__" in stdout:
                start = stdout.index("__SANDBOX_OUTPUT_START__") + len("__SANDBOX_OUTPUT_START__")
                end = stdout.index("__SANDBOX_OUTPUT_END__")
                result_str = stdout[start:end].strip()
                try:
                    return json.loads(result_str)
                except Exception:
                    return result_str
            else:
                return stdout
        finally:
            Path(temp_path).unlink(missing_ok=True)

    @staticmethod
    async def _execute_http(impl: HttpImplementation, **kwargs) -> Any:
        """Execute HTTP API calls"""
        url = impl.url
        # URL Parameter substitution
        for key, value in kwargs.items():
            placeholder = f"{{{key}}}"
            if placeholder in url:
                url = url.replace(placeholder, str(value))

        # Separate parameters already used in the URL
        remaining = {k: v for k, v in kwargs.items() if f"{{{k}}}" not in impl.url}

        params = None
        json_body = None

        if impl.method.upper() == "GET":
            params = remaining
        elif impl.method.upper() in ("POST", "PUT", "PATCH"):
            if impl.body_template:
                # Use templates to replace placeholders
                json_body = SkillExecutor._render_template(impl.body_template, remaining)
            else:
                json_body = remaining

        # Handle variable substitution in headers
        headers = dict(impl.headers) if impl.headers else {}
        for hk, hv in headers.items():
            for key, value in kwargs.items():
                headers[hk] = headers[hk].replace(f"{{{{{key}}}}}", str(value))

        timeout = aiohttp.ClientTimeout(total=impl.timeout)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method=impl.method,
                    url=url,
                    headers=headers or None,
                    params=params,
                    json=json_body,
                ) as response:
                    try:
                        result = await response.json()
                    except Exception:
                        result = await response.text()

                    if response.status >= 400:
                        raise RuntimeError(f"HTTP {response.status}: {result}")

                    # Response field mapping
                    if impl.response_mapping:
                        result = SkillExecutor._apply_response_mapping(
                            result, impl.response_mapping
                        )

                    return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"HTTP Request timeout ({impl.timeout}seconds): {url}")

    @staticmethod
    async def _execute_mcp(impl: McpImplementation, **kwargs) -> Any:
        """Execute MCP Server call

        Connect to the MCP server through MCPClientManager and call the specified tool.
        Supports three transmission protocols: stdio, sse, streamable_http.
        """
        from core.tools.mcp.client_manager import get_mcp_client_manager

        # Construct MCP server configuration based on transport
        transport = (impl.transport or "sse").lower()
        if transport == "stdio":
            # stdio In mode server_url is used as command
            config = {
                "transport_type": "stdio",
                "connection": {"command": impl.server_url, "args": []},
            }
        elif transport in ("sse", "streamable_http"):
            config = {
                "transport_type": transport,
                "connection": {"url": impl.server_url},
            }
        else:
            raise ValueError(f"Unsupported MCP transport protocol: {transport}")

        manager = get_mcp_client_manager()
        # MCPClientManager.call_tool It is a synchronous method (background event loop is used internally),
        # Use asyncio.to_thread to avoid blocking the current event loop
        try:
            result = await asyncio.to_thread(
                manager.call_tool,
                config,
                impl.tool_name,
                kwargs,
                60,
            )
        except Exception as e:
            raise RuntimeError(
                f"MCP Tool call failed (server={impl.server_url}, "
                f"tool={impl.tool_name}): {e}"
            ) from e

        # Attempt to parse string results into JSON for easier downstream processing
        if isinstance(result, str):
            try:
                return json.loads(result)
            except (json.JSONDecodeError, ValueError):
                return result
        return result

    # =========================================================================
    # Helper methods
    # =========================================================================

    @staticmethod
    def _render_template(template: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Render request body template"""
        result = {}
        for key, value in template.items():
            if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
                param_name = value[2:-2].strip()
                result[key] = params.get(param_name, value)
            elif isinstance(value, dict):
                result[key] = SkillExecutor._render_template(value, params)
            else:
                result[key] = value
        return result

    @staticmethod
    def _apply_response_mapping(data: Any, mapping: Dict[str, str]) -> Any:
        """Apply response field mapping"""
        result = {}
        for target_key, source_path in mapping.items():
            value = data
            for part in source_path.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                elif isinstance(value, list) and part.isdigit():
                    value = value[int(part)] if int(part) < len(value) else None
                else:
                    value = None
                    break
            result[target_key] = value
        return result

    @staticmethod
    def create_sync_wrapper(skill: SkillMetadata) -> Callable:
        """
        Create a synchronization wrapper function for the Skill to register to ToolRegistry

        Dynamically generate functions with correct parameter signatures such that LangChain StructuredTool
        Can correctly infer args_schema, allowing Function Calling parameters to be passed correctly.

        Returns:
            Synchronous wrapper function (with correct parameter signature)
        """
        import inspect

        # Build function signature from Skill parameter definition
        params = []
        for p in (skill.parameters or []):
            default = inspect.Parameter.empty if p.required else p.default
            params.append(
                inspect.Parameter(
                    name=p.name,
                    kind=inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                )
            )

        def wrapper(**kwargs):
            return SkillExecutor.execute_sync(skill, **kwargs)

        wrapper.__name__ = skill.name.replace("-", "_")
        wrapper.__doc__ = skill.description

        # Set the correct function signature so LangChain can infer the parameters schema
        if params:
            wrapper.__signature__ = inspect.Signature(parameters=params)

        return wrapper

