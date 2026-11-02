"""Unified analysis execution runner coordinating single and batch stock evaluations."""
from __future__ import annotations

from typing import Any, Dict, Optional
from .provider_resolver import AnalysisProviderResolver
from .result_formatter import has_meaningful_result_payload, normalize_result_data


class AnalysisExecutionRunner:
    """Delegate and normalize single/batch analysis executions."""

    def __init__(self, analysis_service: Any = None) -> None:
        self._service = analysis_service
        self.provider_resolver = AnalysisProviderResolver()

    def get_service(self) -> Any:
        if self._service is None:
            from app.services.simple_analysis_service import get_simple_analysis_service

            self._service = get_simple_analysis_service()
        return self._service

    def format_output(self, raw_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Normalize raw analysis output and attach completeness metadata."""
        if not raw_result:
            return {}
        normalized = normalize_result_data(dict(raw_result))
        normalized["_is_meaningful"] = has_meaningful_result_payload(normalized)
        return normalized
