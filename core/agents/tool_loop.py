"""Iterative tool execution loop and budget guard (`core/agents/tool_loop.py`)."""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger("core.agents.tool_loop")


class ToolExecutionLoop:
    """Manage multi-turn tool invocation, budget limits, and structured error fallback."""

    def __init__(self, max_iterations: int = 8) -> None:
        self.max_iterations = max(1, int(max_iterations))

    def execute_tool_call(
        self,
        tool_map: Dict[str, Any],
        tool_name: str,
        tool_args: Dict[str, Any],
    ) -> str:
        """Invoke a named tool from tool_map and return its string output."""
        target = tool_map.get(tool_name)
        if target is None:
            return f"Tool '{tool_name}' is not registered."
        try:
            if hasattr(target, "invoke"):
                res = target.invoke(tool_args)
            elif callable(target):
                res = target(**tool_args)
            else:
                res = str(target)
            return str(res)
        except Exception as exc:
            logger.warning("Tool '%s' execution error: %s", tool_name, exc)
            return f"Tool '{tool_name}' failed: {exc}"

    def run_bounded_loop(
        self,
        step_fn: Callable[[int], Dict[str, Any]],
        tool_map: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Execute up to max_iterations tool-calling steps until final answer is emitted."""
        history: List[Dict[str, Any]] = []
        for idx in range(self.max_iterations):
            step_out = step_fn(idx)
            history.append(step_out)
            tool_calls = step_out.get("tool_calls") or []
            if not tool_calls:
                break
            for call in tool_calls:
                name = str(call.get("name") or "")
                args = call.get("args") or {}
                call["output"] = self.execute_tool_call(tool_map, name, args)
        return history
