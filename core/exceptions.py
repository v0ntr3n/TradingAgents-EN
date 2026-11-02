"""Typed domain exception hierarchy for TradingAgents (`core/exceptions.py`)."""
from __future__ import annotations

from typing import Any, Dict, Optional


class TradingAgentsError(Exception):
    """Base exception for all TradingAgents domain errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class DataSourceUnavailableError(TradingAgentsError):
    """Raised when an upstream market data provider is unreachable or disabled."""


class DataSourceRateLimitError(TradingAgentsError):
    """Raised when an upstream market data provider throttles requests."""


class DataValidationError(TradingAgentsError):
    """Raised when market, fundamental, or schema validation fails."""


class LLMProviderError(TradingAgentsError):
    """Raised when an LLM API provider call fails or returns invalid output."""


class ToolExecutionError(TradingAgentsError):
    """Raised when an agent tool invocation fails."""


class AgentLoopTimeoutError(TradingAgentsError):
    """Raised when an agent tool-calling or debate loop exceeds its iteration or time budget."""


class ConfigurationError(TradingAgentsError):
    """Raised when system or provider configuration is missing or invalid."""


class AuthenticationError(TradingAgentsError):
    """Raised when user or API authentication fails."""


__all__ = [
    "TradingAgentsError",
    "DataSourceUnavailableError",
    "DataSourceRateLimitError",
    "DataValidationError",
    "LLMProviderError",
    "ToolExecutionError",
    "AgentLoopTimeoutError",
    "ConfigurationError",
    "AuthenticationError",
]
