"""Intelligent assistant streaming dialogue persistence comprehensive regression testing.

Historical bug: stream_chat_with_assistant only saves the conversation after a complete collection of replies,
Timeout/Exception/When the client is disconnected midway, user questions are lost directly.——The question disappears after refreshing the page.
The context is lost and there is no way to investigate. After repair, no matter which path fails, user message and error description
All must be stored.
"""

import asyncio
import json

from app.services import intelligent_assistant_service as service


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


class _Recorder:
    """Log save_assistant_message call parameters."""

    def __init__(self):
        self.saved = []

    async def save(self, db, user_id, user_content, assistant_content,
                   tools_used, conversation_id=None):
        self.saved.append({
            "user_content": user_content,
            "assistant_content": assistant_content,
            "tools_used": tools_used,
        })


def _install_common_stubs(monkeypatch, fake_service_cls, recorder):
    """Replace all external dependencies of stream_chat_with_assistant."""

    async def _none(*args, **kwargs):
        return None

    async def _empty_list(*args, **kwargs):
        return []

    async def _empty_str(*args, **kwargs):
        return ""

    async def _thread(*args, **kwargs):
        return {"thread_id": "thr_test"}

    monkeypatch.setattr(service, "IntelligentAssistantService", fake_service_cls)
    monkeypatch.setattr(service, "_load_assistant_settings", _none)
    monkeypatch.setattr(service, "load_user_profile", _none)
    monkeypatch.setattr(service, "get_assistant_conversation", _empty_list)
    monkeypatch.setattr(service, "_recall_memory_block", _empty_str)
    monkeypatch.setattr(service, "get_or_create_assistant_thread", _thread)
    monkeypatch.setattr(service, "save_assistant_message", recorder.save)


def _collect(agen):
    async def _run():
        return [item async for item in agen]

    return asyncio.run(_run())


def _make_service_cls(events):
    class _FakeService:
        def __init__(self, *args, **kwargs):
            pass

        async def chat_stream(self, *args, **kwargs):
            for item in events:
                yield item

    return _FakeService


def test_stream_error_event_persists_user_message_with_error_note(monkeypatch):
    """Inner layer timeout/exception error event: user questions + The error description must be stored in the library, and done with the error mark."""
    recorder = _Recorder()
    events = [
        _sse("error", {"message": "Processing timed out (more than 180 seconds passed), please try a shorter question."}),
        _sse("done", {"tools_used": [], "data_refs": [], "error": True}),
    ]
    _install_common_stubs(monkeypatch, _make_service_cls(events), recorder)

    items = _collect(service.stream_chat_with_assistant(
        db=object(),
        user_message="Please help me check the sales changes of various models in the industry in the past six months.",
        user_id="u1",
        conversation_id=None,
    ))

    assert recorder.saved, "The failed path must also save user questions"
    saved = recorder.saved[0]
    assert "Ask the world" in saved["user_content"]
    assert "Processing timeout" in saved["assistant_content"]
    # error Events are transparently transmitted to the front end, and the done event is marked with an error
    assert any(item.startswith("event: error\n") and "Processing timeout" in item for item in items)
    assert any(item.startswith("event: done\n") and '"error": true' in item for item in items)


def test_stream_client_disconnect_persists_partial_reply(monkeypatch):
    """The client is disconnected midway (aclose): Some of the collected replies and user questions must be dropped into the database."""
    recorder = _Recorder()

    class _FakeService:
        def __init__(self, *args, **kwargs):
            pass

        async def chat_stream(self, *args, **kwargs):
            yield _sse("token", {"content": "Partial reply"})
            # The client disconnects when the second event has not yet been collected by the outer layer
            yield _sse("token", {"content": "will not be received"})

    _install_common_stubs(monkeypatch, _FakeService, recorder)

    async def _run():
        gen = service.stream_chat_with_assistant(
            db=object(),
            user_message="Generate an excel sheet of estimated testing.",
            user_id="u1",
            conversation_id=None,
        )
        first = await gen.__anext__()
        await gen.aclose()  # Simulate frontend disconnect/timeout abort
        return first

    first = asyncio.run(_run())

    assert "Partial reply" in first
    assert recorder.saved, "The collected content must be saved even if the client is disconnected midway."
    saved = recorder.saved[0]
    assert "excel" in saved["user_content"]
    assert "Partial reply" in saved["assistant_content"]
    assert "will not be received" not in saved["assistant_content"]


def test_stream_success_persists_once(monkeypatch):
    """Normal completion: only save once and save the complete reply."""
    recorder = _Recorder()
    events = [
        _sse("token", {"content": "Normal reply"}),
        _sse("done", {"tools_used": ["t1"], "data_refs": []}),
    ]
    _install_common_stubs(monkeypatch, _make_service_cls(events), recorder)

    items = _collect(service.stream_chat_with_assistant(
        db=object(),
        user_message="Normal question",
        user_id="u1",
        conversation_id=None,
    ))

    assert len(recorder.saved) == 1
    saved = recorder.saved[0]
    assert saved["user_content"] == "Normal question"
    assert saved["assistant_content"] == "Normal reply"
    assert saved["tools_used"] == ["t1"]
    # Normal path done without error flag
    assert not any(item.startswith("event: done\n") and '"error": true' in item for item in items)


def test_stream_outer_exception_sends_error_event_and_persists(monkeypatch):
    """The inner generator throws an exception: the outer layer sends an error event (rather than disguising it as a reply text) and saves part of the reply+Error description."""
    recorder = _Recorder()

    class _BrokenService:
        def __init__(self, *args, **kwargs):
            pass

        async def chat_stream(self, *args, **kwargs):
            yield _sse("token", {"content": "partial"})
            raise RuntimeError("boom")

    _install_common_stubs(monkeypatch, _BrokenService, recorder)

    items = _collect(service.stream_chat_with_assistant(
        db=object(),
        user_message="Ask",
        user_id="u1",
        conversation_id=None,
    ))

    assert recorder.saved, "The outer exception must also save the session"
    saved = recorder.saved[0]
    assert saved["user_content"] == "Ask"
    assert "partial" in saved["assistant_content"]
    assert "boom" in saved["assistant_content"]
    # The frontend receives an explicit error event
    assert any(item.startswith("event: error\n") and "boom" in item for item in items)
    assert any(item.startswith("event: done\n") and '"error": true' in item for item in items)


def test_stream_no_reply_no_error_persists_placeholder(monkeypatch):
    """There is neither reply nor error (extreme scenario): the user s question is still dropped, and the assistant content is a clear placeholder."""
    recorder = _Recorder()
    events = [_sse("done", {"tools_used": [], "data_refs": []})]
    _install_common_stubs(monkeypatch, _make_service_cls(events), recorder)

    _collect(service.stream_chat_with_assistant(
        db=object(),
        user_message="Empty reply question",
        user_id="u1",
        conversation_id=None,
    ))

    assert recorder.saved
    saved = recorder.saved[0]
    assert saved["user_content"] == "Empty reply question"
    assert "Nothing received" in saved["assistant_content"]
