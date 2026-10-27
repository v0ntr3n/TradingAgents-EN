"""
static validator — Code inspection with zero LLM overhead

Four checks:
1. Grammar check — ast.parse()
2. security scan — AST Traverse the blacklist call
3. Dependency check — Parse import and compare whitelist
4. signature consistency — Function parameters vs SkillSpec parameters
"""

import ast
import keyword
import logging
import re
from typing import List, Set

from .skill_spec import GeneratedCode, SkillSpec, ValidationResult

logger = logging.getLogger(__name__)

# Legal Python parameter name patterns (snake_case, etc.); the requirements analysis stage may include HTTP request headers
#  (Such names as headers.User-Agent / headers.Referer) are mistakenly included as function parameters.
# It is impossible to appear in the function signature and is skipped directly during signature comparison to avoid an infinite loop of retries that will inevitably fail.
# Python Keywords (class/import, etc.) cannot be used as parameter names and are skipped altogether.
_VALID_PYTHON_PARAM = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _is_unusable_param_name(name: str) -> bool:
    """Is it possible for a parameter name to appear in a Python function signature (illegal identifier or keyword)"""
    return not _VALID_PYTHON_PARAM.match(name) or keyword.iskeyword(name)


# ==================== blacklist & whitelist ====================

# Security blacklist: functions/modules that are prohibited from being called
SECURITY_BLACKLIST: Set[str] = {
    # System operation
    "os.system", "os.popen", "os.exec", "os.execl", "os.execle",
    "os.execlp", "os.execlpe", "os.execv", "os.execve", "os.execvp",
    "os.execvpe", "os.spawn", "os.spawnl", "os.spawnle",
    "os.remove", "os.rmdir", "os.unlink", "os.rename",
    # child process
    "subprocess.run", "subprocess.call", "subprocess.Popen",
    "subprocess.check_call", "subprocess.check_output",
    # dynamic execution
    "eval", "exec", "compile", "__import__",
    # file writing
    "open",  # Disabled only in write mode (checked in AST)
    # Network (restricted use, partially allowed)
    "socket.socket",
}

# Security blacklist: modules that are prohibited from importing
MODULE_BLACKLIST: Set[str] = {
    "subprocess", "shutil", "ctypes", "multiprocessing",
    "signal", "sys", "code", "codeop", "compileall",
    "importlib", "pickle", "shelve", "marshal",
}

# Placeholder code blacklist (including these strings are considered placeholder implementations and will fail verification)
PLACEHOLDER_PATTERNS: Set[str] = {
    "这里需要实际的",
    "由于无法直接调用",
    "需要配置正确的 API",
    "需要配置 API 密钥",
    "在实际部署时",
    "_generate_mock_data",
    "模拟从聚宽API",
    "模拟API响应",
}

# Allowed core submodules (generated Skills can obtain local data from here)— exact match
ALLOWED_CORE_IMPORTS: Set[str] = {
    "core.skill_runtime.data_access",
    "core.skill_runtime.project_access",
    "core.skill_runtime.standard_financial_apis",
}

# Allowed core submodule prefixes — Prefix matching (for opening the analysis tool subdirectory)
# These are analysis tools under core.tools.implementations, shared with the agent workshop
ALLOWED_CORE_PREFIXES: Set[str] = {
    "core.tools.implementations.fundamentals",
    "core.tools.implementations.market",
    "core.tools.implementations.technical",
    "core.tools.implementations.portfolio",
    "core.tools.implementations.risk",
    "core.tools.implementations.news",
    "core.tools.implementations.social",
    "core.tools.implementations.trade_review",
    "core.tools.implementations.legacy_bridge",
}

# Directly imported project internal implementation modules are prohibited.
# If the generated Skill needs these capabilities, it must be accessed through the public interface of core.skill_runtime.
BLOCKED_IMPORT_PREFIXES: Set[str] = {
    "tradingagents.dataflows.providers",
    "tradingagents.dataflows.interface",
    "hermes_tools",
    "sandbox_tools",
    "skill_build_tools",
    # agent_builder / assistant_ops / skill_builder It is a process tool, and the skill code should not call
    "core.tools.implementations.agent_builder",
    "core.tools.implementations.assistant_ops",
    "core.tools.implementations.skill_builder",
}

# Dependency whitelist: third-party libraries allowed to be imported
DEPENDENCY_WHITELIST: Set[str] = {
    # standard library
    "json", "re", "datetime", "time", "math", "decimal",
    "collections", "itertools", "functools", "typing",
    "urllib", "hashlib", "base64", "copy", "uuid",
    "logging", "traceback", "io", "csv",
    # Allowed third-party libraries
    "requests", "aiohttp", "httpx",
    "pandas", "numpy",
    "akshare",
    "bs4", "lxml",
    "pydantic",
}


class StaticValidator:
    """
    static validator

    Four purely programmatic checks on generated code, with zero LLM overhead and completed in milliseconds.
    """

    def validate(self, code: GeneratedCode, spec: SkillSpec) -> ValidationResult:
        """执行全部四项检查"""
        result = ValidationResult(passed=True)

        # 1. Grammar check
        syntax_ok = self._check_syntax(code.code, result)
        if not syntax_ok:
            result.passed = False
            return result

        # 2. security scan
        tree = ast.parse(code.code)
        self._check_security(tree, result)

        # 3. Dependency check
        self._check_dependencies(tree, result)

        # 4. signature consistency
        self._check_signature(tree, code.code, spec, result)

        # 5. Placeholder code detection
        self._check_placeholder_code(code.code, result)

        # 6. Interface specification URL verbatim comparison (to prevent LLM from rewriting the path, such as rank_data → rank/data) 
        self._check_interface_urls(code.code, spec, result)

        if result.errors:
            result.passed = False

        result.details["checks_run"] = 6
        return result

    # ==================== Check 1: Grammar ====================

    def _check_interface_urls(self, code: str, spec: SkillSpec, result: ValidationResult) -> None:
        """Interface specification URL bidirectional verification.

        Forward: The URL given in the specification must appear in the code as it is (to prevent LLM from rewriting the path,
        Such as rank_data → rank/data, Wasted iterations after sandbox 404).
        Reverse: The interface endpoints appearing in the code must come from the specification (to prevent LLM from fabricating new endpoints)
        Mappings such as brand resolution, such as brand/all, select_series_v2, all 404).
        query string (?a=b) Not included in comparison——Example parameters should be implemented as function parameters and should not be hardcoded.
        URL Matching is limited to ASCII URL characters: when Chinese is closely attached to the URL (such as rank_data initiates a request )
        It must be truncated, otherwise the contaminated string will be compared and the correct code will be accidentally killed.
        """
        import re as _re

        spec_base_urls: list[str] = []
        for constraint in spec.constraints or []:
            for m in _re.finditer(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", str(constraint)):
                base_url = m.group(0).split("?")[0].rstrip(".,;:")
                spec_base_urls.append(base_url)
                if base_url not in code:
                    result.errors.append(
                        f"Interface URL rewriting violation: The code does not contain the interface URL specified by the specification.{base_url}] . "
                        "The interface path must use the original specification verbatim, and rewriting the path is strictly prohibited (for example, rank_data must not be written as rank/data)"
                    )
                else:
                    logger.debug(f"[StaticValidator] Interface URL verbatim verification passed: {base_url}")

        # Reverse: fake endpoint check (enabled only when the specification contains the interface URL)
        if spec_base_urls:
            reported: set[str] = set()
            for m in _re.finditer(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", code):
                code_base = m.group(0).split("?")[0].rstrip(".,;:")
                if code_base in spec_base_urls or code_base in reported:
                    continue
                reported.add(code_base)
                result.errors.append(
                    f"Fabricated interface endpoint violation: The interface appearing in the code {code_base}] Not in the specs."
                    "It is strictly forbidden to make up interface endpoints not mentioned in the specifications (historical lessons: make up brand/all,"
                    "select_series_v2 etc. Brand parsing endpoints all 404); business filtering (such as brand→car model mapping)"
                    "When the interface does not support it, it must be implemented locally based on the pulled data. If it cannot be overridden, it will be included in the output."
                    "Clearly state the data boundaries of The interface does not contain a brand field, and the results may be incomplete "
                )

    def _check_syntax(self, code: str, result: ValidationResult) -> bool:
        """Grammar check — ast.parse()"""
        try:
            ast.parse(code)
            return True
        except SyntaxError as e:
            result.errors.append(f"语法错误 (行 {e.lineno}): {e.msg}")
            return False

    # ==================== Check 2: safe ====================

    def _check_security(self, tree: ast.AST, result: ValidationResult) -> None:
        """security scan — AST Traverse the blacklist call"""
        for node in ast.walk(tree):
            # Check function calls
            if isinstance(node, ast.Call):
                call_name = self._get_call_name(node)
                if call_name and call_name in SECURITY_BLACKLIST:
                    result.errors.append(f"安全违规: 禁止调用 {call_name}")

            # Check open() writing mode
            if isinstance(node, ast.Call) and self._get_call_name(node) == "open":
                if len(node.args) >= 2:
                    mode_arg = node.args[1]
                    if isinstance(mode_arg, ast.Constant) and "w" in str(mode_arg.value):
                        result.errors.append("security violation: Disable opening files in write mode")
                # Check keyword arguments mode=
                for kw in node.keywords:
                    if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                        if "w" in str(kw.value.value) or "a" in str(kw.value.value):
                            result.errors.append("security violation: Disable opening files in write/append mode")

    def _get_call_name(self, node: ast.Call) -> str:
        """Extract function name from AST Call node"""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            return ".".join(reversed(parts))
        return ""


    # ==================== Check 3: Depend on ====================

    def _check_dependencies(self, tree: ast.AST, result: ValidationResult) -> None:
        """Dependency check — Parse the import statement and compare it with the whitelist"""
        imported_modules: List[str] = []
        imported_full: List[str] = []

        for node in ast.walk(tree):
            # import xxx
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    top_level = name.split(".")[0]
                    imported_modules.append(top_level)
                    imported_full.append(name)
            # from xxx import yyy
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imported_full.append(node.module)
                    top_level = node.module.split(".")[0]
                    imported_modules.append(top_level)

        for full_mod in set(imported_full):
            blocked_prefix = next(
                (prefix for prefix in BLOCKED_IMPORT_PREFIXES if full_mod == prefix or full_mod.startswith(prefix + ".")),
                None,
            )
            if blocked_prefix:
                result.errors.append(
                    f"禁止直接导入: {full_mod}（请改用 core.skill_runtime.data_access 或 core.skill_runtime.project_access）"
                )
                continue

            if full_mod in ALLOWED_CORE_IMPORTS:
                continue
            # Prefix matching: allow submodules under ALLOWED_CORE_PREFIXES
            allowed_prefix = next(
                (prefix for prefix in ALLOWED_CORE_PREFIXES if full_mod == prefix or full_mod.startswith(prefix + ".")),
                None,
            )
            if allowed_prefix:
                continue
            top_level = full_mod.split(".")[0]
            if top_level == "core":
                result.errors.append(f"禁止导入: {full_mod}（仅允许 core.skill_runtime.* 和 core.tools.implementations 分析类子目录）")
                continue

        for mod in set(imported_modules):
            if mod in MODULE_BLACKLIST:
                result.errors.append(f"禁止导入模块: {mod}")
            elif mod not in DEPENDENCY_WHITELIST and mod != "core":
                result.warnings.append(f"未知依赖: {mod}（不在白名单中，可能需要额外安装）")

        result.details["imported_modules"] = list(set(imported_modules))

    # ==================== Check 4: signature consistency ====================

    def _check_signature(
        self,
        tree: ast.AST,
        code: str,
        spec: SkillSpec,
        result: ValidationResult,
    ) -> None:
        """signature consistency — Function parameters vs SkillSpec parameters"""
        # found being @tool Decorated function, or first top-level function
        target_func: ast.FunctionDef | None = None
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                target_func = node
                # If the function name matches spec.tool_id, it will be used first
                if node.name == spec.tool_id:
                    break

        if target_func is None:
            result.errors.append("未找到顶层函数定义")
            return

        # Extract function parameter names (excluding self)
        func_params: List[str] = []
        for arg in target_func.args.args:
            if arg.arg != "self":
                func_params.append(arg.arg)

        # Compare parameters in SkillSpec (skipping illegal Python identifiers/keyword arguments like headers.User-Agent)
        spec_params = {p.name for p in spec.parameters}
        skipped = {name for name in spec_params if _is_unusable_param_name(name)}
        if skipped:
            logger.warning(
                f"[StaticValidator] SkillSpec Contains illegal Python identifier parameter, signature comparison skipped: {sorted(skipped)}"
            )
        spec_params -= skipped
        func_params_set = set(func_params)

        missing_in_func = spec_params - func_params_set
        extra_in_func = func_params_set - spec_params

        if missing_in_func:
            result.errors.append(
                f"Function is missing parameters defined in SkillSpec: {', '.join(sorted(missing_in_func))}"
            )
        if extra_in_func:
            result.warnings.append(
                f"Function contains extra parameters not defined in SkillSpec: {', '.join(sorted(extra_in_func))}"
            )

        result.details["function_name"] = target_func.name
        result.details["function_params"] = func_params
        result.details["spec_params"] = list(spec_params)

    # ==================== Check 5: Placeholder code ====================

    def _check_placeholder_code(self, code: str, result: ValidationResult) -> None:
        """Placeholder code detection — Code containing placeholder comments/fake implementations is prohibited"""
        for pattern in PLACEHOLDER_PATTERNS:
            if pattern in code:
                result.errors.append(
                    f"Placeholder code prohibited: The code contains {pattern}] , Real data acquisition logic must be implemented"
                )

