"""
Strategy Evaluator
- DSL Assessment: L2 (Semantic)→ L3 (execution)
- Python+config Evaluation: L2 (config check)→ L3 (/run_python execution)
"""
import copy
import logging
from typing import Any, Dict, List, Optional, Tuple

from .dsl_validator import validate_dsl_semantics
from .engine_client import BacktestEngineClient

logger = logging.getLogger(__name__)


def validate_config_semantics(config: Dict[str, Any]) -> List[str]:
    """
    L2 Semantic verification: Verify config (symbols are not empty, dates are reasonable, etc.)
    Returns:
        Error list, empty means pass
    """
    errors: List[str] = []
    symbols = config.get("symbols")
    if not symbols:
        uni = config.get("universe") or {}
        symbols = uni.get("symbols", []) if isinstance(uni, dict) else []
    if not symbols:
        errors.append("Stock pool symbols cannot be empty")

    start_year = config.get("start_year")
    end_year = config.get("end_year")
    if start_year is not None and end_year is not None:
        try:
            sy, ey = int(start_year), int(end_year)
            if sy >= ey:
                errors.append(f"Backtest interval start_year({sy}) should be less than end_year({ey})")
        except (TypeError, ValueError):
            pass

    max_pos = config.get("max_positions", 10)
    if symbols and max_pos is not None and int(max_pos) < 1:
        errors.append("max_positions at least for 1")
    return errors


def _make_lightweight_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate lightweight config for L3 execution verification (shortened interval, single standard)
    """
    lightweight = copy.deepcopy(config)
    symbols = lightweight.get("symbols")
    if not symbols:
        uni = lightweight.get("universe") or {}
        symbols = (uni.get("symbols", []) or []) if isinstance(uni, dict) else []
    if symbols:
        if "symbols" in lightweight:
            lightweight["symbols"] = [symbols[0]]
        else:
            uni = lightweight.setdefault("universe", {})
            if isinstance(uni, dict):
                uni["symbols"] = [symbols[0]]
    lightweight["start_year"] = 2024
    lightweight["end_year"] = 2024
    return lightweight


async def validate_execution_python(
    code: str, config: Dict[str, Any]
) -> Tuple[bool, Optional[str]]:
    """
    L3 Execution verification: do a lightweight backtest on the Python strategy to verify whether it can run through
    Returns:
        (success, error_message)
    """
    try:
        client = BacktestEngineClient()
        lightweight = _make_lightweight_config(config)
        resp = await client.run_python(code, lightweight)
        if resp.get("success"):
            return True, None
        return False, resp.get("error", "Backtest execution failed")
    except Exception as e:
        logger.warning("L3 Execution check exception: %s", e)
        return False, str(e)


async def evaluate_strategy_python_full(
    code: str,
    config: Dict[str, Any],
    run_execution_check: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Full evaluation: L2 config verification + L3 Execute (optional)
    Returns:
        (passed, errors)
    """
    errors = validate_config_semantics(config)
    if errors:
        return False, errors
    if run_execution_check:
        ok, exec_err = await validate_execution_python(code, config)
        if not ok and exec_err:
            errors.append(f"Failed to perform verification: {exec_err}")
            return False, errors
    return True, []


def _make_lightweight_dsl(dsl: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate lightweight DSL for L3 execution verification (shortened interval, single standard)
    Only verify whether it can run through, don t care about the income
    """
    lightweight = copy.deepcopy(dsl)
    cfg = lightweight.setdefault("config", {})
    uni = lightweight.get("universe", {})
    symbols = uni.get("symbols", []) if isinstance(uni, dict) else []
    if symbols:
        lightweight["universe"] = {
            **uni,
            "symbols": [symbols[0]],
        }
    cfg["start_year"] = 2024
    cfg["end_year"] = 2024
    return lightweight


async def validate_execution(dsl: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    L3 Execute verification: do a lightweight backtest on the DSL to verify whether it can run through
    Returns:
        (success, error_message)
    """
    try:
        client = BacktestEngineClient()
        lightweight = _make_lightweight_dsl(dsl)
        resp = await client.run(lightweight)
        if resp.get("success"):
            return True, None
        return False, resp.get("error", "Backtest execution failed")
    except Exception as e:
        logger.warning("L3 Execution check exception: %s", e)
        return False, str(e)


def evaluate_dsl(dsl: Dict[str, Any]) -> List[str]:
    """
    L2 Semantic check
    Returns:
        Error list, empty means pass
    """
    return validate_dsl_semantics(dsl)


async def evaluate_dsl_full(
    dsl: Dict[str, Any],
    run_execution_check: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Full assessment: L2 semantics + L3 Execute (optional)
    Returns:
        (passed, errors)
    """
    errors = evaluate_dsl(dsl)
    if errors:
        return False, errors
    if run_execution_check:
        ok, exec_err = await validate_execution(dsl)
        if not ok and exec_err:
            errors.append(f"Failed to perform verification: {exec_err}")
            return False, errors
    return True, []
