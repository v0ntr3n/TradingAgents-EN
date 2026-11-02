# -*- coding: utf-8 -*-
"""
Skill Streaming display of code generation thinking process — Unit testing

Coverage:
1. OpenAICompatAdapter.chat_stream_deltas: reasoning/content incremental output
2. UnifiedLLMClient.chat_stream: Incremental callback + Complete content splicing
3. UnifiedLLMClient.chat_stream: Fallback to normal when adapter does not support streaming chat
"""
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from core.llm.models import LLMConfig, LLMProvider, LLMResponse, Message
from core.llm.providers.openai_compat import OpenAICompatAdapter
from core.llm.unified_client import UnifiedLLMClient


def _make_adapter() -> OpenAICompatAdapter:
    config = LLMConfig(
        provider=LLMProvider.DEEPSEEK,
        model="deepseek-reasoner",
        api_key="test-key",
        base_url="https://api.deepseek.com",
        timeout=60,
        retry_times=1,
    )
    return OpenAICompatAdapter(config)


def _make_chunk(reasoning: Optional[str] = None, content: Optional[str] = None):
    delta = SimpleNamespace(reasoning_content=reasoning, content=content)
    choice = SimpleNamespace(delta=delta)
    return SimpleNamespace(choices=[choice])


class _FakeStreamClient:
    """Simulate streaming returns from OpenAI sync client"""

    def __init__(self, chunks):
        self._chunks = chunks
        outer = self

        class _Completions:
            def create(self, **kwargs):
                assert kwargs.get("stream") is True
                return iter(outer._chunks)

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()


class _FakeNonStreamAdapter:
    """Adapter without chat_stream_deltas, verify fallback path"""

    def __init__(self):
        self.config = LLMConfig(
            provider=LLMProvider.DEEPSEEK,
            model="deepseek-chat",
            api_key="test-key",
            timeout=60,
            retry_times=1,
        )

    def chat(self, messages, tools=None, **kwargs) -> LLMResponse:
        return LLMResponse(content="Full reply", model="deepseek-chat", finish_reason="stop")


def _messages() -> List[Message]:
    return [Message(role="user", content="Generate code")]


def test_adapter_stream_yields_reasoning_and_content():
    adapter = _make_adapter()
    adapter._sync_client = _FakeStreamClient([
        _make_chunk(reasoning="Analyze needs first"),
        _make_chunk(reasoning=", Let s look at the data structure again"),
        _make_chunk(content="```python"),
        _make_chunk(content="\nprint('hi')\n```"),
    ])

    deltas = list(adapter.chat_stream_deltas(_messages(), max_tokens=128))

    assert deltas == [
        {"type": "reasoning", "text": "Analyze needs first"},
        {"type": "reasoning", "text": ", Let s look at the data structure again"},
        {"type": "content", "text": "```python"},
        {"type": "content", "text": "\nprint('hi')\n```"},
    ]


def test_client_chat_stream_collects_content_and_calls_on_delta():
    adapter = _make_adapter()
    adapter._sync_client = _FakeStreamClient([
        _make_chunk(reasoning="Thinking"),
        _make_chunk(content="print"),
        _make_chunk(content="('hi')"),
    ])
    client = UnifiedLLMClient(adapter)

    events: List[Dict[str, str]] = []
    response = client.chat_stream(
        _messages(),
        on_delta=lambda kind, text: events.append({"kind": kind, "text": text}),
        max_tokens=128,
    )

    assert response.content == "print('hi')"
    assert response.model == "deepseek-reasoner"
    assert events == [
        {"kind": "reset", "text": ""},
        {"kind": "reasoning", "text": "Thinking"},
        {"kind": "content", "text": "print"},
        {"kind": "content", "text": "('hi')"},
    ]


def test_client_chat_stream_falls_back_to_chat_without_stream_adapter():
    client = UnifiedLLMClient(_FakeNonStreamAdapter())

    events: List[Dict[str, str]] = []
    response = client.chat_stream(
        _messages(),
        on_delta=lambda kind, text: events.append({"kind": kind, "text": text}),
        max_tokens=128,
    )

    assert response.content == "Full reply"
    assert events == [{"kind": "content", "text": "Full reply"}]
