#!/usr/bin/env python3
"""
TradingAgents Runtime configuration adapter (weak dependency)

- Prioritizes trying to read dynamic system_settings from backend app.services.config_provider if available
- If unavailable or unable to wait synchronously in an asynchronous event loop, fallback to environment variables and default values
- Maintain the independence of the TradingAgents package: silently fall back when unavailable, without introducing hard dependencies
"""

from __future__ import annotations

import os
import asyncio
from typing import Any, Optional, Callable

import logging
_logger = logging.getLogger("tradingagents.config")


def _get_event_loop_running() -> bool:
    """Detect if there is an event loop running"""
    try:
        # get_running_loop A RuntimeError will be thrown when there is no event loop (quieter, no warnings will be triggered)
        loop = asyncio.get_running_loop()
        return loop is not None and loop.is_running()
    except RuntimeError:
        return False
    except Exception:
        # Other exceptions also think there is no event loop
        return False


def _get_system_settings_sync() -> dict:
    """Best effort to get backend dynamic system_settings.
    - If the backend is unavailable/not installed, return empty dict
    - If there is currently an event loop running, to avoid deadlock/nesting, return empty directly. dict

    NOTE: To avoid event loop conflicts, the current implementation always returns an empty dictionary,
    Rely on environment variables and default values for configuration.
    """
    # Temporary solution: Disable dynamic configuration retrieval completely to avoid event loop conflicts
    # TODO: In the future, you can consider using thread pools or other methods to safely obtain dynamic configurations.
    _logger.debug("Dynamic configuration fetching is disabled, use environment variables and default values")
    return {}

    # The following code is temporarily commented to avoid event loop conflicts
    # # first inspection
    # if _get_event_loop_running():
    #     _logger.debug("Event loop is running, skipping dynamic configuration acquisition")
    #     return {}

    # try:
    #     # Delay import to avoid hard dependencies
    #     from app.services.config_provider import provider as config_provider  # type: ignore

    #     # Second check: Make sure the event loop is not started during the import process
    #     if _get_event_loop_running():
    #         _logger.debug("Event loop detected after import, skipping dynamic configuration acquisition")
    #         return {}

    #     # Third check: Confirm again before calling asyncio.run
    #     try:
    #         # Try to get the current event loop. If successful, it means there is a loop running.
    #         current_loop = asyncio.get_running_loop()
    #         if current_loop and current_loop.is_running():
    #             _logger.debug("asyncio.run A running event loop is detected before calling and skipped")
    #             return {}
    #     except RuntimeError:
    #         # There is no running event loop and it is safe to call asyncio.run
    #         pass

    #     # Use asyncio.run to make one-time synchronous calls
    #     return asyncio.run(config_provider.get_effective_system_settings()) or {}

    # except RuntimeError as e:
    #     error_msg = str(e).lower()
    #     if any(keyword in error_msg for keyword in [
    #         "cannot be called from a running event loop",
    #         "got future attached to a different loop",
    #         "task was destroyed but it is pending"
    #     ]):
    #         _logger.debug(f"Event loop conflict detected, skipping dynamic configuration fetch: {e}")
    #         return {}
    #     _logger.debug(f"Failed to obtain dynamic configuration (RuntimeError): {e}")
    #     return {}
    # except Exception as e:
    #     _logger.debug(f"Failed to obtain dynamic configuration: {e}")
    #     return {}


def _coerce(value: Any, caster: Callable[[Any], Any], default: Any) -> Any:
    try:
        if value is None:
            return default
        return caster(value)
    except Exception:
        return default


def get_number(env_var: str, system_key: Optional[str], default: float | int, caster: Callable[[Any], Any]) -> float | int:
    """Get numerical configuration by priority:DB(system_settings) > ENV > default
    - env_var: Environment variable name, for example "TA_US_MIN_API_INTERVAL_SECONDS"
    - system_key: Dynamic system setting key name, for example "ta_us_min_api_interval_seconds" (Can be None)
    - default: Default value
    - caster: Type conversion functions such as float or int
    """
    # 1) DB Dynamic settings
    if system_key:
        eff = _get_system_settings_sync()
        if isinstance(eff, dict) and system_key in eff:
            return _coerce(eff.get(system_key), caster, default)

    # 2) environment variables
    env_val = os.getenv(env_var)
    if env_val is not None and str(env_val).strip() != "":
        return _coerce(env_val, caster, default)

    # 3) Code default
    return default


def get_float(env_var: str, system_key: Optional[str], default: float) -> float:
    return get_number(env_var, system_key, default, float)  # type: ignore[arg-type]


def get_int(env_var: str, system_key: Optional[str], default: int) -> int:
    return get_number(env_var, system_key, default, int)  # type: ignore[arg-type]


# --- Boolean access helper ---------------------------------------------------

def get_bool(env_var: str, system_key: Optional[str], default: bool) -> bool:
    """Get boolean configuration by priority:DB(system_settings) > ENV > default"""
    # 1) DB Dynamic settings
    if system_key:
        eff = _get_system_settings_sync()
        if isinstance(eff, dict) and system_key in eff:
            v = eff.get(system_key)
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(v)
            if isinstance(v, str):
                return str(v).strip().lower() in ("1", "true", "yes", "on")
    # 2) environment variables
    env_val = os.getenv(env_var)
    if env_val is not None and str(env_val).strip() != "":
        return str(env_val).strip().lower() in ("1", "true", "yes", "on")
    # 3) Code default
    return default


def use_app_cache_enabled(default: bool = False) -> bool:
    """Whether to enable preferential reading from the app cache (Mongo collection).ENV: TA_USE_APP_CACHE; DB: ta_use_app_cache
    An evaluation log will be recorded, including the source and original ENV value, to facilitate troubleshooting the effective path.
    """
    # Inferred source (DB/ENV/DEFAULT)
    src = "default"
    env_val = os.getenv("TA_USE_APP_CACHE")
    try:
        eff = _get_system_settings_sync()
    except Exception:
        eff = {}
    if isinstance(eff, dict) and "ta_use_app_cache" in eff:
        src = "db"
    elif env_val is not None and str(env_val).strip() != "":
        src = "env"

    # final value (following DB > ENV > DEFAULT) 
    val = get_bool("TA_USE_APP_CACHE", "ta_use_app_cache", default)

    try:
        _logger.info(f"[runtime_settings] TA_USE_APP_CACHE evaluated -> {val} (source={src}, env={env_val})")
    except Exception:
        pass
    return val


# --- Timezone access helpers -------------------------------------------------
from typing import Optional as _Optional
from zoneinfo import ZoneInfo as _ZoneInfo


def get_timezone_name(default: str = "Asia/Shanghai") -> str:
    """Return configured timezone name with priority: DB(system_settings) > ENV > default.
    - DB key: app_timezone (preferred) or APP_TIMEZONE
    - ENV vars checked in order: APP_TIMEZONE, TIMEZONE, TA_TIMEZONE
    """
    try:
        eff = _get_system_settings_sync()
        if isinstance(eff, dict):
            tz = eff.get("app_timezone") or eff.get("APP_TIMEZONE")
            if isinstance(tz, str) and tz.strip():
                return tz.strip()
    except Exception:
        pass

    for env_key in ("APP_TIMEZONE", "TIMEZONE", "TA_TIMEZONE"):
        val = os.getenv(env_key)
        if isinstance(val, str) and val.strip():
            return val.strip()

    return default


def get_zoneinfo(default: str = "Asia/Shanghai") -> _ZoneInfo:
    """Convenience: return ZoneInfo for the configured timezone name."""
    name = get_timezone_name(default)
    try:
        return _ZoneInfo(name)
    except Exception:
        # Fallback to UTC if invalid
        return _ZoneInfo("UTC")


__all__ = [
    "get_float",
    "get_int",
    "get_bool",
    "use_app_cache_enabled",
    "get_timezone_name",
    "get_zoneinfo",
]
