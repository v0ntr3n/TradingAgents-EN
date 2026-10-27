import asyncio

from app.services import im_topic_digest_service as digest_module


def test_digest_session_thread_uses_llm_summary(monkeypatch):
    captured = {
        "summary_calls": 0,
        "append_content": "",
        "update_payload": None,
    }

    async def fake_build_summary(db, messages, title=""):
        captured["summary_calls"] += 1
        assert title == "External session precipitation"
        return {
            "abstract": "External communication revolves around whether CATL s short-term gains are too rapid, and the current conclusion is biased towards high levels of shock rather than extreme bubbles.",
            "confirmed_facts": ["Price divergences and technical positions have been discussed in the latest round"],
            "open_questions": ["Whether to continue to supplement industry prosperity verification"],
            "next_actions": ["Continue to track subsequent profit realization and momentum changes"],
            "focus_score": 0.82,
        }

    async def fake_append_message(db, user_id, role, content, conversation_id=None, tools_used=None):
        captured["append_content"] = content
        return conversation_id

    async def fake_summarize_thread(db, user_id, conversation_id=None, summary_type="manual"):
        return {"abstract": "ok"}

    monkeypatch.setattr(digest_module, "_build_thread_summary_with_llm", fake_build_summary)
    monkeypatch.setattr(digest_module, "append_assistant_message", fake_append_message)
    monkeypatch.setattr(digest_module, "summarize_assistant_thread", fake_summarize_thread)

    service = digest_module.IMTopicDigestService(_FakeDB(captured))
    monkeypatch.setattr(service, "_resolve_target_thread_id", _async_return("topic-1"))

    session_thread = {
        "user_id": "user-1",
        "thread_id": "im-1",
        "message_count": 6,
        "last_digest_message_count": 0,
    }

    digested = asyncio.run(service._digest_session_thread(session_thread, min_messages=2, lookback_limit=10))

    assert digested is True
    assert captured["summary_calls"] == 1
    assert "High volatility rather than extreme bubble" in captured["append_content"]
    assert "Confirmed information:" in captured["append_content"]
    assert captured["update_payload"]["$set"]["last_digest_summary"].startswith("External communication revolves around CATL")


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def skip(self, count):
        if count <= 0:
            return self
        self._docs = self._docs[count:]
        return self

    async def to_list(self, length=None):
        if length is None:
            return list(self._docs)
        return list(self._docs[:length])


class _FakeMessagesCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, query):
        return _FakeCursor(list(self._docs))


class _FakeThreadsCollection:
    def __init__(self, captured):
        self._captured = captured

    async def update_one(self, query, payload):
        self._captured["update_payload"] = payload


class _FakeDB:
    def __init__(self, captured):
        self.assistant_thread_messages = _FakeMessagesCollection(
            [
                {"role": "user", "content": "It probably rose too much during the Ningde era."},
                {"role": "assistant", "content": "I ll first look at it by price deviation and technical position."},
                {"role": "user", "content": "The main concern is whether it has overheated."},
                {"role": "assistant", "content": "At present, it seems that the price is rising rapidly, and we need to continue to look at it based on the industry prosperity."},
            ]
        )
        self.assistant_threads = _FakeThreadsCollection(captured)


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner