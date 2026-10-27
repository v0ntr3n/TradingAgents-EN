"""
sandbox executor — Child process runs generated code in isolation

Core features:
- subprocess Isolated execution (independent process to prevent contamination of the main process)
- 30 seconds timeout protection
- stdout / stderr / return value capture
- Resource limits (memory, CPU time)
"""

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from core.python_runtime import resolve_python_executable
from .skill_spec import SandboxResult, SkillSpec

logger = logging.getLogger(__name__)

# Default timeout (seconds)
DEFAULT_TIMEOUT = 30


class SandboxRunner:
    """
    sandbox executor

    Run the generated Python code in a separate subprocess, capturing output and return values.
    """

    # Decorator pattern that needs to be stripped out of generated code
    _DECORATOR_PATTERNS = [
        r"^\s*@tool\b.*$",
        r"^\s*@register_tool\b.*$",
    ]
    # Import patterns that need to be stripped from generated code
    _IMPORT_STRIP_PATTERNS = [
        r"^\s*from\s+core\.tools\.base\s+import\b.*$",
        r"^\s*from\s+langchain_core\.tools\s+import\s+tool\b.*$",
    ]

    def __init__(self, timeout: int = DEFAULT_TIMEOUT):
        self.timeout = timeout
        # Project root directory (used to set PYTHONPATH)
        self._project_root = str(Path(__file__).parent.parent.parent.parent)
        self._python_executable = resolve_python_executable(
            self._project_root,
            env_var_names=("TRADINGAGENTS_SANDBOX_PYTHON_EXE", "TRADINGAGENTS_PYTHON_EXE"),
        )

    def run(
        self,
        code: str,
        spec: SkillSpec,
        test_input: Optional[Dict[str, Any]] = None,
    ) -> SandboxResult:
        """
        Execute generated code in a sandbox

        Args:
            code: Complete Python function code
            spec: Skill Specification (used to determine function names and test inputs)
            test_input: Test input parameters (takes precedence over spec.test_input)

        Returns:
            SandboxResult: Execution result
        """
        test_args = test_input or spec.test_input or {}
        start_time = time.time()

        # Construct execution script
        runner_script = self._build_runner_script(code, spec.tool_id, test_args)

        try:
            result = self._execute_in_subprocess(runner_script)
            result.execution_time = round(time.time() - start_time, 3)
            return result
        except Exception as e:
            logger.error(f"沙箱执行异常: {e}")
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time=round(time.time() - start_time, 3),
            )

    def run_diagnostic_script(
        self,
        script: str,
        *,
        allowed_tools: Optional[Sequence[str]] = None,
    ) -> SandboxResult:
        """Execute the build-time diagnostic script and inject the hermes_tools RPC equivalent stub.

        This capability is only used during the Agentic Skill generation phase to confirm the real field/interface return shape.
        Not allowed to enter the final Skill product; the final code is still intercepted by StaticValidator for dependencies such as hermes_tools.
        """
        start_time = time.time()
        logger.info(
            "🧪 [DiagnosticSandbox] start script_chars=%s allowed_tools=%s timeout=%s",
            len(script or ""),
            list(allowed_tools or []),
            self.timeout,
        )
        try:
            runner_script = self._build_diagnostic_runner_script(
                script,
                allowed_tools=allowed_tools,
            )
            result = self._execute_in_subprocess(runner_script)
            result.execution_time = round(time.time() - start_time, 3)
            logger.info(
                "🧪 [DiagnosticSandbox] done success=%s execution_time=%.3fs error=%s stdout_chars=%s stderr_chars=%s",
                result.success,
                result.execution_time,
                result.error,
                len(result.stdout or ""),
                len(result.stderr or ""),
            )
            return result
        except Exception as e:
            logger.error("诊断沙箱执行异常: %s", e)
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time=round(time.time() - start_time, 3),
            )

    def _strip_decorators_and_imports(self, code: str) -> str:
        """
        Strip decorators and project-specific imports from generated code

        Even if CodeGenerator s prompt explicitly disables decorators,
        LLM It is still possible to generate a file with @tool / @register_tool code.
        This is the last line of defense.
        """
        lines = code.split("\n")
        cleaned = []
        all_patterns = self._DECORATOR_PATTERNS + self._IMPORT_STRIP_PATTERNS
        for line in lines:
            skip = False
            for pat in all_patterns:
                if re.match(pat, line):
                    skip = True
                    break
            if not skip:
                cleaned.append(line)
        return "\n".join(cleaned)

    def _build_runner_script(
        self, code: str, func_name: str, test_args: Dict[str, Any]
    ) -> str:
        """构造沙箱执行脚本"""
        # Strip the decorators and project imports first
        clean_code = self._strip_decorators_and_imports(code)
        args_json = json.dumps(test_args, ensure_ascii=False)
        # Use textwrap.dedent to ensure consistent indentation
        script = textwrap.dedent(f"""\
            import json
            import os
            import sys

            PROJECT_ROOT = r"{self._project_root}"
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            os.chdir(PROJECT_ROOT)

            # ===== generated code =====
            {textwrap.indent(clean_code, '            ').strip()}
            # ===== end =====

            if __name__ == "__main__":
                try:
                    import types as _types
                    test_args = json.loads('''{args_json}''')
                    # Find objective function
                    func = None
                    for name, obj in list(locals().items()):
                        if callable(obj) and name == "{func_name}":
                            func = obj
                            break
                    if func is None:
                        # Fallback: Find the first user-defined function that does not start with _
                        # Exclude non-Skill functions such as types (such as datetime), modules, built-in functions, typing types, imported functions, etc.
                        import typing as _typing
                        _skip_names = {{"json", "sys", "os", "_types", "_typing", "test_args", "func", "name", "obj"}}
                        for name, obj in list(locals().items()):
                            if name.startswith("_") or name in _skip_names:
                                continue
                            if not callable(obj):
                                continue
                            # Only accepts functions (lambda or def), excludes classes/types
                            if isinstance(obj, type):
                                continue
                            # Exclude modules
                            if isinstance(obj, _types.ModuleType):
                                continue
                            # Exclude built-in functions
                            if isinstance(obj, _types.BuiltinFunctionType):
                                continue
                            # Exclude typing types (Optional, Dict, List, Any etc.)
                            # typing._SpecialForm is callable but not a type, it will be mistaken for a function
                            if hasattr(obj, "__module__") and getattr(obj, "__module__", "").startswith("typing"):
                                continue
                            # Exclude typing._GenericAlias instances (such as Dict[str, Any]) 
                            if hasattr(_typing, "_GenericAlias") and isinstance(obj, _typing._GenericAlias):
                                continue
                            if hasattr(_typing, "_SpecialForm") and isinstance(obj, _typing._SpecialForm):
                                continue
                            # Exclude functions from import (non-user defined)
                            # User-defined function __module__ is "__main__", import The function that comes to __module__ is the package path
                            obj_module = getattr(obj, "__module__", "")
                            if obj_module and obj_module != "__main__":
                                continue
                            func = obj
                            break
                    if func is None:
                        print(json.dumps({{"__error__": "No executable function found"}}))
                        sys.exit(1)

                    result = func(**test_args)
                    print("__SANDBOX_OUTPUT_START__")
                    print(json.dumps(result, ensure_ascii=False, default=str))
                    print("__SANDBOX_OUTPUT_END__")
                except Exception as e:
                    print(json.dumps({{"__error__": str(e)}}), file=sys.stderr)
                    sys.exit(1)
        """)
        return script

    def _build_diagnostic_runner_script(
        self,
        script: str,
        *,
        allowed_tools: Optional[Sequence[str]] = None,
    ) -> str:
        """Construct a build-time diagnostic script and provide the hermes_tools stub."""
        allowed = list(allowed_tools or (
            "run_readonly_query",
            "probe_interface",
            "inspect_collection_schema",
            "describe_runtime_helper",
        ))
        allowed_json = json.dumps(allowed, ensure_ascii=False)
        user_script = str(script or "")
        return textwrap.dedent(f"""\
            import json
            import os
            import sys
            import types

            PROJECT_ROOT = r"{self._project_root}"
            if PROJECT_ROOT not in sys.path:
                sys.path.insert(0, PROJECT_ROOT)
            os.chdir(PROJECT_ROOT)

            _ALLOWED_TOOLS = set(json.loads('''{allowed_json}'''))
            _CALL_COUNT = 0
            _MAX_CALLS = 12

            def _call_build_tool(name, *args, **kwargs):
                global _CALL_COUNT
                if name not in _ALLOWED_TOOLS:
                    raise PermissionError(f"diagnostic tool not allowed: {{name}}")
                _CALL_COUNT += 1
                if _CALL_COUNT > _MAX_CALLS:
                    raise RuntimeError("diagnostic tool call limit exceeded")
                from core.tools.external import recon_tools
                func = getattr(recon_tools, name, None)
                if not callable(func):
                    raise RuntimeError(f"diagnostic tool not found: {{name}}")
                raw = func(*args, **kwargs)
                try:
                    return json.loads(raw)
                except Exception:
                    return raw

            hermes_tools = types.ModuleType("hermes_tools")
            for _name in _ALLOWED_TOOLS:
                setattr(hermes_tools, _name, (lambda tool_name: (lambda *args, **kwargs: _call_build_tool(tool_name, *args, **kwargs)))(_name))
            sys.modules["hermes_tools"] = hermes_tools

            if __name__ == "__main__":
                try:
                    _globals = {{"__name__": "__diagnostic__"}}
                    exec({user_script!r}, _globals, _globals)
                    result = _globals.get("result", _globals.get("RESULT", None))
                    print("__SANDBOX_OUTPUT_START__")
                    print(json.dumps({{"result": result, "tool_call_count": _CALL_COUNT}}, ensure_ascii=False, default=str))
                    print("__SANDBOX_OUTPUT_END__")
                except Exception as e:
                    print(json.dumps({{"__error__": str(e)}}), file=sys.stderr)
                    sys.exit(1)
        """)

    def _execute_in_subprocess(self, script: str) -> SandboxResult:
        """在子进程中执行脚本"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write(script)
            temp_path = f.name

        # Set PYTHONPATH so that child processes can find project modules (safety net)
        env = os.environ.copy()
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = self._project_root + (os.pathsep + existing if existing else "")

        try:
            logger.debug("Skill Sandbox usage Python: %s", self._python_executable)
            proc = subprocess.run(
                [self._python_executable, temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=self._project_root,
                env=env,
            )

            stdout = proc.stdout.strip()
            stderr = proc.stderr.strip()

            # Extract return value
            output = None
            if "__SANDBOX_OUTPUT_START__" in stdout:
                start = stdout.index("__SANDBOX_OUTPUT_START__") + len("__SANDBOX_OUTPUT_START__")
                end = stdout.index("__SANDBOX_OUTPUT_END__")
                raw = stdout[start:end].strip()
                try:
                    output = json.loads(raw)
                except json.JSONDecodeError:
                    output = raw

            if proc.returncode != 0:
                error_msg = stderr
                if stderr:
                    try:
                        err_data = json.loads(stderr)
                        if "__error__" in err_data:
                            error_msg = err_data["__error__"]
                    except json.JSONDecodeError:
                        pass
                return SandboxResult(
                    success=False, output=output,
                    stdout=stdout, stderr=stderr, error=error_msg,
                )

            return SandboxResult(
                success=True, output=output,
                stdout=stdout, stderr=stderr,
            )

        except subprocess.TimeoutExpired:
            return SandboxResult(
                success=False,
                error=f"执行超时（{self.timeout}s）",
            )
        finally:
            Path(temp_path).unlink(missing_ok=True)

