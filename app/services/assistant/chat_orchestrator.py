"""Orchestrator for research assistant chat turns and context injection."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from .prompt_builder import AssistantPromptBuilder
from .report_attachment import AssistantReportAttachment


class AssistantChatOrchestrator:
    """Coordinate report attachment formatting and prompt assembly for assistant turns."""

    def __init__(self) -> None:
        self.prompt_builder = AssistantPromptBuilder()
        self.attachment_helper = AssistantReportAttachment()

    def prepare_turn(
        self,
        user_query: str,
        history: Optional[List[Dict[str, str]]] = None,
        attached_reports: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, str]]:
        """Build final LLM message list for an assistant conversation turn."""
        ctx = self.attachment_helper.format_attachments(attached_reports or {})
        return self.prompt_builder.build_messages(user_query, history=history, context_block=ctx)
