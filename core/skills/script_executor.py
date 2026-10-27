"""
Scripted Skill Executor

Responsible for executing local scripted Skills (Skill packages installed from ClawHub).

Core functions:
1. {baseDir} Variable substitution - Inject the Skill package directory path into the script execution environment
2. Script execution - execution via subprocess scripts/*.py
3. Credential injection - Inject configured environment variables into the child process (Phase 2 implementation)

Execution process:
    1. Get skill_dir and script_path
    2. Set the baseDir environment variable to skill_dir
    3. Inject credentials environment variables (if any)
    4. execute scripts/*.py, Pass in parameters
    5. Capture stdout/stderr and return the result
"""

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ScriptSkillExecutor:
    """Scripted Skill Executor

    Used to execute Python scripts from local Skill packages installed from ClawHub.
    support {baseDir} Variable substitution and credential injection.
    """

    # Default execution timeout (seconds)
    DEFAULT_TIMEOUT = 60
    # {baseDir} Variable name (OpenClaw standard)
    BASE_DIR_VAR = "baseDir"

    @staticmethod
    def execute_cli(
        skill_dir: str,
        script_path: str,
        args: Optional[List[str]] = None,
        credentials: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        python_executable: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute Skill script with command line parameters

        Suitable for scripts that expect command line arguments (such as fetch_data.py "Query content" --start-date ...) . 

        Args:
            skill_dir: Skill Package directory absolute path
            script_path: Script relative paths (e.g. "scripts/fetch_data.py") 
            args: A list of command line arguments (e.g. ["Federal Reserve Interest Rate Policy", "--start-date", "2025-01-01T00:00:00"]) 
            credentials: Credential environment variables
            timeout: Timeout seconds
            python_executable: Python interpreter

        Returns:
            {success, result, stdout, stderr, error, execution_time_ms, exit_code}
        """
        start = time.time()

        skill_dir_path = Path(skill_dir).resolve()
        full_script_path = skill_dir_path / script_path

        if not full_script_path.exists():
            return {
                "success": False, "result": None, "stdout": "", "stderr": "",
                "error": f"Script file does not exist: {full_script_path}",
                "execution_time_ms": int((time.time() - start) * 1000), "exit_code": -1,
            }

        # Build environment variables
        env = os.environ.copy()
        env[ScriptSkillExecutor.BASE_DIR_VAR] = str(skill_dir_path)
        if credentials:
            for key, value in credentials.items():
                if value is not None:
                    env[key] = str(value)

        # Build command:python script.py arg1 arg2 ...
        # Use the current Python interpreter by default (make sure to use the same venv dependency as the project)
        if not python_executable:
            python_executable = sys.executable or "python"
        cmd = [python_executable, str(full_script_path)]
        if args:
            cmd.extend(args)

        logger.info(
            f"🔧 CLI execute: {' '.join(cmd)} (cwd={skill_dir_path.name}, timeout={timeout}s)"
        )

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                cwd=str(skill_dir_path),
                encoding="utf-8",
                errors="replace",
            )

            execution_time_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                parsed = ScriptSkillExecutor._parse_output(result.stdout)
                return {
                    "success": True,
                    "result": parsed,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "error": None if not result.stderr else result.stderr,
                    "execution_time_ms": execution_time_ms,
                    "exit_code": 0,
                }
            else:
                # Bring both stderr and stdout for easy diagnosis
                error_msg = (result.stderr or "").strip() or (result.stdout or "").strip() or f"exit code: {result.returncode}"
                return {
                    "success": False,
                    "result": None,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "error": error_msg,
                    "execution_time_ms": execution_time_ms,
                    "exit_code": result.returncode,
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False, "result": None, "stdout": "", "stderr": "",
                "error": f"Execution timeout ({timeout}seconds)",
                "execution_time_ms": int((time.time() - start) * 1000), "exit_code": -1,
            }
        except Exception as e:
            logger.error(f"❌ CLI Execution exception: {e}", exc_info=True)
            return {
                "success": False, "result": None, "stdout": "", "stderr": "",
                "error": str(e),
                "execution_time_ms": int((time.time() - start) * 1000), "exit_code": -1,
            }

    @staticmethod
    def execute(
        skill_dir: str,
        script_path: str,
        args: Optional[Dict[str, Any]] = None,
        credentials: Optional[Dict[str, str]] = None,
        timeout: int = DEFAULT_TIMEOUT,
        python_executable: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute skill script

        Args:
            skill_dir: Skill Package directory absolute path (for {baseDir} replacement)
            script_path: Script relative paths (e.g. "scripts/fetch_data.py") 
            args: Parameters passed to the script (JSON via stdin)
            credentials: Credentials environment variables (Phase 2 implementation, currently optional)
            timeout: Timeout seconds
            python_executable: Python interpreter path

        Returns:
            {
                "success": bool,
                "result": Any,  # stdout Parse results
                "stdout": str,  # original stdout
                "stderr": str,
                "error": Optional[str],
                "execution_time_ms": int,
                "exit_code": int
            }
        """
        start = time.time()

        # Build script full path
        skill_dir_path = Path(skill_dir).resolve()
        full_script_path = skill_dir_path / script_path

        if not full_script_path.exists():
            return {
                "success": False,
                "result": None,
                "stdout": "",
                "stderr": "",
                "error": f"Script file does not exist: {full_script_path}",
                "execution_time_ms": int((time.time() - start) * 1000),
                "exit_code": -1,
            }

        # Build environment variables
        env = os.environ.copy()
        # {baseDir} Replacement: Inject the Skill package directory path into the environment variable
        env[ScriptSkillExecutor.BASE_DIR_VAR] = str(skill_dir_path)
        # Credential injection (Phase 2 implementation, currently optional)
        if credentials:
            for key, value in credentials.items():
                if value is not None:
                    env[key] = str(value)

        # Build command
        # Use the current Python interpreter by default (make sure to use the same venv dependency as the project)
        if not python_executable:
            python_executable = sys.executable or "python"
        cmd = [python_executable, str(full_script_path)]

        # Prepare input parameters (pass in JSON via stdin)
        input_data = json.dumps(args, ensure_ascii=False) if args else ""

        try:
            logger.info(
                f"🔧 Execute script type Skill: {cmd[0]} {full_script_path.name} "
                f"(skill_dir={skill_dir_path.name}, timeout={timeout}s)"
            )

            result = subprocess.run(
                cmd,
                input=input_data,
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout,
                cwd=str(skill_dir_path),
                encoding="utf-8",
                errors="replace",
            )

            execution_time_ms = int((time.time() - start) * 1000)

            if result.returncode == 0:
                # Try parsing stdout as JSON
                parsed_result = ScriptSkillExecutor._parse_output(result.stdout)
                return {
                    "success": True,
                    "result": parsed_result,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "error": None if not result.stderr else result.stderr,
                    "execution_time_ms": execution_time_ms,
                    "exit_code": 0,
                }
            else:
                return {
                    "success": False,
                    "result": None,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "error": result.stderr or f"Script exit code: {result.returncode}",
                    "execution_time_ms": execution_time_ms,
                    "exit_code": result.returncode,
                }

        except subprocess.TimeoutExpired:
            execution_time_ms = int((time.time() - start) * 1000)
            logger.warning(f"⏰ Script execution timeout ({timeout}s) : {full_script_path}")
            return {
                "success": False,
                "result": None,
                "stdout": "",
                "stderr": "",
                "error": f"Execution timeout ({timeout}seconds)",
                "execution_time_ms": execution_time_ms,
                "exit_code": -1,
            }
        except FileNotFoundError as e:
            execution_time_ms = int((time.time() - start) * 1000)
            return {
                "success": False,
                "result": None,
                "stdout": "",
                "stderr": "",
                "error": f"Python Interpreter does not exist: {python_executable} ({e})",
                "execution_time_ms": execution_time_ms,
                "exit_code": -1,
            }
        except Exception as e:
            execution_time_ms = int((time.time() - start) * 1000)
            logger.error(f"❌ Script execution exception: {e}", exc_info=True)
            return {
                "success": False,
                "result": None,
                "stdout": "",
                "stderr": "",
                "error": str(e),
                "execution_time_ms": execution_time_ms,
                "exit_code": -1,
            }

    @staticmethod
    def replace_base_dir(text: str, skill_dir: str) -> str:
        """Replace Skill package directory variable in text

        OpenClaw Skill In the standard, scripts and directives reference the Skill package root using the following variables:
        - {baseDir} - OpenClaw official standard variables
        - ${baseDir} - Shell style variables
        - <skill_dir> - Variables used by some ClawHub Skills (such as ifind-repilot)

        This function replaces all these variables with the actual skill_dir path.

        Args:
            text: text containing variables
            skill_dir: Skill Package directory absolute path

        Returns:
            Replaced text
        """
        if not text:
            return text
        # Unified path separator (Windows compatible)
        normalized_dir = skill_dir.replace("\\", "/")
        return (
            text
            .replace("{baseDir}", normalized_dir)
            .replace("${baseDir}", normalized_dir)
            .replace("<skill_dir>", normalized_dir)
        )

    @staticmethod
    def prepare_script_args(skill_doc: Dict[str, Any], call_args: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare script call parameters

        Extract skill_dir and script_path from Skill doc,
        and perform parameter values {baseDir} Replace.

        Args:
            skill_doc: MongoDB Skill documentation in
            call_args: Call parameters

        Returns:
            {
                "skill_dir": str,
                "script_path": str,
                "args": Dict (replaced {baseDir}),
                "credentials": Dict (Extracted from doc, stage 2 implementation)
            }
        """
        skill_dir = skill_doc.get("skill_dir", "")
        impl = skill_doc.get("implementation") or {}
        script_path = impl.get("script_path", "")

        # Perform on parameter values {baseDir} replace
        prepared_args = {}
        for key, value in call_args.items():
            if isinstance(value, str):
                prepared_args[key] = ScriptSkillExecutor.replace_base_dir(value, skill_dir)
            else:
                prepared_args[key] = value

        return {
            "skill_dir": skill_dir,
            "script_path": script_path,
            "args": prepared_args,
            "credentials": {},  # Phase 2 implementation: loading from skill_credentials collection
        }

    @staticmethod
    def _parse_output(stdout: str) -> Any:
        """Parse script output

        First try to parse to JSON, if failed, return the original string.

        Args:
            stdout: Script stdout

        Returns:
            Parsed result (dict/list/str)
        """
        if not stdout:
            return None

        stdout_stripped = stdout.strip()

        # Try parsing directly as JSON
        try:
            return json.loads(stdout_stripped)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to extract a JSON chunk from the output (possibly in a markdown code chunk)
        import re
        json_block_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", stdout_stripped, re.DOTALL)
        if json_block_match:
            try:
                return json.loads(json_block_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Try looking for the __SANDBOX_OUTPUT_START__ / __SANDBOX_OUTPUT_END__ tags
        sandbox_match = re.search(
            r"__SANDBOX_OUTPUT_START__\s*(.*?)\s*__SANDBOX_OUTPUT_END__",
            stdout_stripped,
            re.DOTALL,
        )
        if sandbox_match:
            try:
                return json.loads(sandbox_match.group(1).strip())
            except (json.JSONDecodeError, ValueError):
                return sandbox_match.group(1).strip()

        # Return the original string (truncated output that is too long)
        if len(stdout_stripped) > 5000:
            return stdout_stripped[:5000] + "...(truncated)"
        return stdout_stripped
