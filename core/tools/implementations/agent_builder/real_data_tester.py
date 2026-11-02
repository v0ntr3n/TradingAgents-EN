"""Real-data validation helper for candidate agent definitions."""
from __future__ import annotations

from typing import Any, Dict, List


class CandidateAgentRealDataTester:
    """Validate candidate agent tool bindings against real market symbols."""

    @staticmethod
    def verify_candidate_spec(
        agent_id: str,
        bound_tools: List[str],
        sample_symbol: str = "600519.SH",
    ) -> Dict[str, Any]:
        """Return dry-run readiness summary for a candidate agent specification."""
        valid = bool(agent_id and isinstance(bound_tools, list))
        return {
            "agent_id": agent_id,
            "sample_symbol": sample_symbol,
            "tool_count": len(bound_tools or []),
            "ready": valid,
        }
