"""
plan executor

Schedule tool calls according to DAG dependencies in AnalysisPlan:
- Dependency-free steps are executed in parallel using asyncio.gather
- There are dependent steps that wait to be executed after the dependencies are completed.
- Single step timeout is 60s, the overall timeout is controlled by the caller

Dependencies:
- core/tools/registry.py — Tool function acquisition
- core/agents/planner_models.py — data model
"""

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from core.tools import get_tool_registry

from .planner_models import AnalysisPlan, PlanStep, StepResult

logger = logging.getLogger(__name__)

# Single step execution timeout (seconds)
STEP_TIMEOUT_SECONDS = 60


class PlanExecutor:
    """
    plan executor

    According to the depends_on relationship of steps in AnalysisPlan,
    Group parallel/serial execution tool calls by topological ordering.
    """

    def __init__(self):
        self._registry = get_tool_registry()

    async def execute(
        self,
        plan: AnalysisPlan,
        on_step_started: Optional[Callable] = None,
        on_step_completed: Optional[Callable] = None,
    ) -> List[StepResult]:
        """
        Perform all steps in the analysis plan.

        Args:
            plan: analysis plan
            on_step_started: step start callback (step_id, tool, intent)
            on_step_completed: Step completion callback (StepResult)

        Returns:
            List of execution results of all steps
        """
        if not plan.steps:
            return []

        all_results: Dict[int, StepResult] = {}
        groups = plan.parallel_groups

        for group in groups:
            tasks = [
                self._execute_step(step, on_step_started, on_step_completed)
                for step in group
            ]
            group_results = await asyncio.gather(*tasks, return_exceptions=True)

            for step, result in zip(group, group_results):
                if isinstance(result, Exception):
                    sr = StepResult(
                        step_id=step.id,
                        tool=step.tool,
                        intent=step.intent,
                        success=False,
                        error=str(result),
                    )
                    if on_step_completed:
                        on_step_completed(sr)
                    all_results[step.id] = sr
                else:
                    all_results[step.id] = result

        # Return sorted by step ID
        return [all_results[sid] for sid in sorted(all_results.keys())]

    async def _execute_step(
        self,
        step: PlanStep,
        on_started: Optional[Callable] = None,
        on_completed: Optional[Callable] = None,
    ) -> StepResult:
        """Perform a single step"""
        if on_started:
            on_started(step.id, step.tool, step.intent)

        start_time = time.time()

        func = self._registry.get_function(step.tool)
        if func is None:
            sr = StepResult(
                step_id=step.id,
                tool=step.tool,
                intent=step.intent,
                success=False,
                error=f"Tools '{step.tool}' Unregistered or no function implementation",
            )
            if on_completed:
                on_completed(sr)
            return sr

        try:
            result = await asyncio.wait_for(
                self._invoke_tool(func, step.args),
                timeout=STEP_TIMEOUT_SECONDS,
            )
            duration_ms = int((time.time() - start_time) * 1000)

            sr = StepResult(
                step_id=step.id,
                tool=step.tool,
                intent=step.intent,
                success=True,
                result=result,
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            sr = StepResult(
                step_id=step.id,
                tool=step.tool,
                intent=step.intent,
                success=False,
                error=f"Tool execution timeout ({STEP_TIMEOUT_SECONDS}s) ",
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            sr = StepResult(
                step_id=step.id,
                tool=step.tool,
                intent=step.intent,
                success=False,
                error=str(e),
                duration_ms=duration_ms,
            )

        if on_completed:
            on_completed(sr)
        return sr

    @staticmethod
    async def _invoke_tool(func: Callable, args: Dict[str, Any]) -> Any:
        """Call tool functions (automatically handle synchronous/asynchronous)"""
        # Defense layer: Filter out parameters that are not accepted by tool functions to avoid LLM self-created parameters causing TypeError
        try:
            sig = inspect.signature(func)
            valid_params = set(sig.parameters.keys())
            # Check if there is **kwargs, If there is, do not filter
            has_var_keyword = any(
                p.kind == inspect.Parameter.VAR_KEYWORD
                for p in sig.parameters.values()
            )
            if not has_var_keyword:
                filtered_args = {k: v for k, v in args.items() if k in valid_params}
                if len(filtered_args) != len(args):
                    removed = set(args.keys()) - valid_params
                    logger.warning(
                        f"[PlanExecutor] Filtered tools {func.__name__} Unsupported parameters: {removed}"
                    )
                args = filtered_args
        except (ValueError, TypeError):
            pass  # No filtering when signature cannot be obtained

        if inspect.iscoroutinefunction(func):
            return await func(**args)
        else:
            # Synchronous functions are executed in the thread pool to avoid blocking the event loop
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, lambda: func(**args))

