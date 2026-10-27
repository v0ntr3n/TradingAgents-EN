"""Skill Runtime asynchronous bridging and result normalization."""

from __future__ import annotations

import asyncio
from threading import Thread
from typing import Any, Dict


def run_async_in_sync(coro: Any) -> Any:
    """Safely execute coroutines in a synchronized context.

    Args:
        coro: Coroutine object to be executed (coroutine)

    Returns:
        Any: Coroutine execution result; if there is currently a running event loop, the coroutine will be executed in an independent daemon thread and the result will be returned.
            Exceptions in the child thread will be re-thrown to the caller
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    outcome: Dict[str, Any] = {}

    def _runner() -> None:
        try:
            outcome["result"] = asyncio.run(coro)
        except Exception as exc:
            outcome["error"] = exc

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("result")


def normalize_tabular_result(data: Any) -> Any:
    """Normalize tabular objects such as DataFrame into serializable results.

    Args:
        data: Arbitrary input data, may be None / pandas.DataFrame / or other objects

    Returns:
        Any: Standardized results, rules——
            - Returns when input is None None
            - When the input is a table object with to_dict:
                - If the index is not the default RangeIndex or named, reset_index first and then to_dict("records"), Return list[dict]
                - If to_dict("records") Fallback on failure to_dict(), Return dict
            - Other inputs are returned unchanged
    """
    if data is None:
        return None
    if hasattr(data, "to_dict"):
        try:
            tabular = data
            if hasattr(tabular, "reset_index") and hasattr(tabular, "index"):
                index_name = getattr(tabular.index, "name", None)
                index_type = type(tabular.index).__name__
                if index_name or index_type != "RangeIndex":
                    tabular = tabular.reset_index()
            return tabular.to_dict("records")
        except TypeError:
            return data.to_dict()
    return data