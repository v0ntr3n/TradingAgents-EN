from __future__ import annotations
import sys as _sys
_self_mod = _sys.modules[__name__]
for _sub in ['retry', 'report_aggregator']:
    _sys.modules[f"core.utils.{_sub}"] = _self_mod
    setattr(_self_mod, _sub, _self_mod)

# === retry.py ===
"""
Unified retry tool

Provides retryable exception judgment and synchronous/asynchronous exponential backoff retry functions.
For sharing by UnifiedLLMClient, AgentBase and other modules.
"""

import asyncio
import logging
import random
import time
from typing import Any, Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_KEYWORDS = (
    "choices", "null value", "connection", "timeout", "timed out",
    "rate limit", "too many requests", "server error", "500", "502", "503", "529",
    # Current limiting tips for domestic gateways such as JD Cloud
    "429", "rate_limit", "tokens limit", "rate_limited", "Access restrictions", "RATE_LIMIT",
)


def is_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(kw in msg for kw in RETRYABLE_KEYWORDS)


def retry_sync(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = 3,
    max_wait: int = 10,
    label: str = "retry_sync",
    retryable: Optional[Callable[[Exception], bool]] = None,
    **kwargs: Any,
) -> T:
    """Synchronous exponential backoff retries.

    Args:
        fn: The callable to retry
        max_retries: Maximum number of retries (excluding first call)
        max_wait: Backoff upper limit seconds
        label: log tag
        retryable: Customized retryable judgment function, used by default is_retryable
    """
    _retryable = retryable or is_retryable
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # exponential backoff + Random jitter to avoid multiple requests synchronously retrying to form a storm (such as 429 current limiting scenario)
                wait = min(2 ** attempt, max_wait) + random.uniform(0, 1)
                logger.info("[%s] Wait for %.1fs and try again (%d/%d)...", label, wait, attempt, max_retries)
                time.sleep(wait)
            return fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _retryable(e) and attempt < max_retries:
                logger.warning("[%s] The call failed (can be retried): %s", label, e)
                continue
            raise
    raise last_err  # type: ignore[misc]  # pragma: no cover


async def retry_async(
    fn: Callable[..., Awaitable[T]],
    *args: Any,
    max_retries: int = 3,
    max_wait: int = 10,
    label: str = "retry_async",
    retryable: Optional[Callable[[Exception], bool]] = None,
    **kwargs: Any,
) -> T:
    """Asynchronous exponential backoff retries."""
    _retryable = retryable or is_retryable
    last_err: Optional[Exception] = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                # exponential backoff + Random jitter to avoid multiple requests synchronously retrying to form a storm (such as 429 current limiting scenario)
                wait = min(2 ** attempt, max_wait) + random.uniform(0, 1)
                logger.info("[%s] Wait for %.1fs and try again (%d/%d)...", label, wait, attempt, max_retries)
                await asyncio.sleep(wait)
            return await fn(*args, **kwargs)
        except Exception as e:
            last_err = e
            if _retryable(e) and attempt < max_retries:
                logger.warning("[%s] The call failed (can be retried): %s", label, e)
                continue
            raise
    raise last_err  # type: ignore[misc]  # pragma: no cover

# === report_aggregator.py ===
"""
Report aggregator

Dynamically obtain all analysis reports instead of hard-coded field acquisition

Usage:
    
    # Method 1: Use convenience functions
    reports = get_all_reports(state)
    curr_situation = reports.to_text()
    
    # Way 2: Use classes
    aggregator = ReportAggregator()
    reports = aggregator.aggregate(state)
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .agents.analyst_registry import get_analyst_registry
from .agents.config import AgentMetadata, BUILTIN_AGENTS

# Import logs
from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")


@dataclass
class AggregatedReports:
    """Aggregated report collection"""
    
    reports: Dict[str, str] = field(default_factory=dict)  # {field_name: content}
    labels: Dict[str, str] = field(default_factory=dict)   # {field_name: label}
    order: List[str] = field(default_factory=list)         # Field names in order of execution
    
    def get(self, field_name: str, default: str = "") -> str:
        """Get specified report"""
        return self.reports.get(field_name, default)
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary"""
        return self.reports.copy()
    
    def to_text(self, separator: str = "\n\n") -> str:
        """
        Convert to text (in order of execution, with labels)
        
        Returns:
            Formatted report text
        """
        parts = []
        for field_name in self.order:
            content = self.reports.get(field_name, "")
            if content:
                label = self.labels.get(field_name, "")
                if label:
                    parts.append(f"{label}\n{content}")
                else:
                    parts.append(content)
        return separator.join(parts)
    
    def to_text_simple(self, separator: str = "\n\n") -> str:
        """
        Convert to text (without tags, for backward compatibility)
        """
        parts = []
        for field_name in self.order:
            content = self.reports.get(field_name, "")
            if content:
                parts.append(content)
        return separator.join(parts)
    
    def __len__(self) -> int:
        return len([r for r in self.reports.values() if r])


class ReportAggregator:
    """
    Report aggregator
    
    Dynamically obtain all analysis reports from state
    """
    
    # Default reporting fields (backwards compatible)
    DEFAULT_FIELDS = [
        ("index_report", " [Macro market analysis]", 1),
        ("sector_report", " [Industry sector analysis]", 5),
        ("market_report", " [Technical analysis]", 10),
        ("sentiment_report", " [Public opinion analysis]", 20),
        ("news_report", " [News Analysis]", 30),
        ("fundamentals_report", " [Fundamental Analysis]", 40),
    ]
    
    def __init__(self, use_registry: bool = True):
        """
        Initialize aggregator
        
        Args:
            use_registry: Whether to use the registry to obtain fields (False uses the default fields)
        """
        self.use_registry = use_registry
        self._field_config: Optional[List[tuple]] = None
    
    def _get_field_config(self) -> List[tuple]:
        """Get field configuration [(field_name, label, order), ...]"""
        if self._field_config is not None:
            return self._field_config
        
        if self.use_registry:
            config = []
            # Obtained from built-in Agent metadata
            for agent_id, metadata in BUILTIN_AGENTS.items():
                if metadata.output_field:
                    config.append((
                        metadata.output_field,
                        metadata.report_label or "",
                        metadata.execution_order
                    ))
            
            # Get additional ones from the registry (if any)
            registry = get_analyst_registry()
            for analyst_id in registry.list_all():
                meta = registry.get_analyst_metadata(analyst_id)
                if meta and meta.output_field:
                    # avoid duplication
                    if not any(f[0] == meta.output_field for f in config):
                        config.append((
                            meta.output_field,
                            meta.report_label or "",
                            meta.execution_order
                        ))
            
            # Sort by execution order
            self._field_config = sorted(config, key=lambda x: x[2])
        else:
            self._field_config = self.DEFAULT_FIELDS
        
        return self._field_config
    
    def aggregate(self, state: Dict[str, Any]) -> AggregatedReports:
        """
        Aggregate all reports from state
        
        Args:
            state: Workflow status dictionary
            
        Returns:
            AggregatedReports Example
        """
        result = AggregatedReports()
        
        for field_name, label, order in self._get_field_config():
            content = state.get(field_name, "")
            if content:
                result.reports[field_name] = content
                result.labels[field_name] = label
                result.order.append(field_name)
        
        logger.debug(f"📊 [Report aggregation] Get {len(result)} report")
        return result
    
    def get_report_fields(self) -> List[str]:
        """Get all report field names"""
        return [f[0] for f in self._get_field_config()]


# global instance
_aggregator: Optional[ReportAggregator] = None


def get_aggregator() -> ReportAggregator:
    """Get global aggregator instance"""
    global _aggregator
    if _aggregator is None:
        _aggregator = ReportAggregator()
    return _aggregator


def get_all_reports(state: Dict[str, Any]) -> AggregatedReports:
    """
    Convenience function: get all reports from state
    
    Usage:
        reports = get_all_reports(state)
        curr_situation = reports.to_text()
    """
    return get_aggregator().aggregate(state)


# === __init__.py ===
"""
Core tool module
"""

__all__ = [
    "ReportAggregator",
    "AggregatedReports", 
    "get_aggregator",
    "get_all_reports",
]
