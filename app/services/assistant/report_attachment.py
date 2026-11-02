"""Report attachment extractor for assistant chat sessions."""
from __future__ import annotations

from typing import Any, Dict, List


class AssistantReportAttachment:
    """Format attached stock analysis reports into concise context snippets."""

    @staticmethod
    def format_attachments(reports: Dict[str, Any], max_chars: int = 2000) -> str:
        """Concatenate non-empty report sections up to max_chars."""
        if not isinstance(reports, dict):
            return ""
        parts: List[str] = []
        for key, val in reports.items():
            if isinstance(val, str) and val.strip():
                parts.append(f"### {key}\n{val.strip()[:600]}")
        combined = "\n\n".join(parts)
        return combined[:max_chars]
