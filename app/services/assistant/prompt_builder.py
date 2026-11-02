"""Assistant prompt construction combining user query, conversation history, and attachments."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class AssistantPromptBuilder:
    """Assemble structured system and user messages for the research assistant."""

    @staticmethod
    def build_messages(
        user_query: str,
        history: Optional[List[Dict[str, str]]] = None,
        context_block: str = "",
    ) -> List[Dict[str, str]]:
        """Build message list with optional attached report context."""
        sys_text = (
            "You are a financial research assistant. Provide factual, compliance-safe "
            "analysis grounded in disclosed financial data."
        )
        if context_block:
            sys_text = f"{sys_text}\n\nAttached Context:\n{context_block}"
        messages: List[Dict[str, str]] = [{"role": "system", "content": sys_text}]
        for turn in history or []:
            role = str(turn.get("role") or "user")
            content = str(turn.get("content") or "")
            if content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": str(user_query or "")})
        return messages
