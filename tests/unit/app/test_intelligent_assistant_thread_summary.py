import asyncio
from types import SimpleNamespace

from app.services import intelligent_assistant_service as service
from core.llm.models import LLMConfig, LLMProvider
from core.llm.models import LLMResponse


def test_build_thread_summary_with_llm_prefers_structured_output(monkeypatch):
    messages = [
        {"role": "user", "content": "It probably rose too much during the Ningde era."},
        {
            "role": "assistant",
            "content": (
                "The data is back, let s talk with numbers. The short-term increase is relatively fast, but the RSI is not overbought yet."
                "More like a high shock than an extreme bubble."
            ),
        },
    ]

    class DummyClient:
        async def achat(self, messages):
            return LLMResponse(
                content=(
                    '{"abstract":"CATL s short-term gains are relatively fast, but it is currently closer to highs and experiencing strong fluctuations, and no extreme overheating signals have yet appeared.",'
                    '"confirmed_facts":["The latest round of replies has compared price deviation, RSI and valuation positions","The conclusion is that the short-term rise is rapid, but it is not an extreme state of bubbles."],'
                    '"open_questions":["Whether we should continue to look at the industry boom and subsequent profit realization"],'
                    '"next_actions":["Continue to supplement industry prosperity and profit growth verification","Observe whether the subsequent momentum continues to weaken"],'
                    '"focus_score":0.86}'
                )
            )

    monkeypatch.setattr(service, "get_coding_llm_config", _async_return(_fake_llm_config()))
    monkeypatch.setattr(service.UnifiedLLMClient, "from_config", lambda config: DummyClient())

    summary = asyncio.run(service._build_thread_summary_with_llm(db=object(), messages=messages, title="Ningde era"))

    assert summary["abstract"] == "CATL s short-term gains are relatively fast, but it is currently closer to highs and experiencing strong fluctuations, and no extreme overheating signals have yet appeared."
    assert summary["confirmed_facts"][0] == "The latest round of replies has compared price deviation, RSI and valuation positions"
    assert summary["open_questions"] == ["Whether we should continue to look at the industry boom and subsequent profit realization"]
    assert summary["next_actions"][0] == "Continue to supplement industry prosperity and profit growth verification"
    assert summary["focus_score"] == 0.86


def test_build_thread_summary_with_llm_falls_back_when_llm_fails(monkeypatch):
    messages = [
        {"role": "user", "content": "It probably rose too much during the Ningde era."},
        {"role": "assistant", "content": "The data is back, we use numbers to speak, not feelings. It is organized as follows:\n\n## Current status\n The price deviates more from the moving average."},
    ]

    class BrokenClient:
        async def achat(self, messages):
            raise RuntimeError("llm unavailable")

    monkeypatch.setattr(service, "get_coding_llm_config", _async_return(_fake_llm_config()))
    monkeypatch.setattr(service.UnifiedLLMClient, "from_config", lambda config: BrokenClient())

    summary = asyncio.run(service._build_thread_summary_with_llm(db=object(), messages=messages, title="Ningde era"))

    assert summary == service._build_thread_summary_from_messages(messages, "Ningde era")
    assert summary["abstract"].startswith("Data is back")


def test_build_thread_summary_with_llm_falls_back_when_client_init_fails(monkeypatch):
    messages = [
        {"role": "user", "content": "Does CATL conform to the concept of value investing?"},
        {"role": "assistant", "content": "I break it down from three levels: valuation, earnings quality and cash flow."},
    ]

    monkeypatch.setattr(service, "get_coding_llm_config", _async_return(_fake_llm_config()))

    def _raise_client_error(config):
        raise RuntimeError("client init failed")

    monkeypatch.setattr(service.UnifiedLLMClient, "from_config", _raise_client_error)

    summary = asyncio.run(service._build_thread_summary_with_llm(db=object(), messages=messages, title="Ningde era"))

    assert summary == service._build_thread_summary_from_messages(messages, "Ningde era")
    assert summary["focus_score"] > 0


def test_thread_doc_to_item_hides_legacy_raw_abstract_summary():
    item = service._thread_doc_to_item(
        {
            "thread_id": "thr_legacy",
            "title": "Ningde era",
            "topic_type": "general",
            "pinned": False,
            "archived": False,
            "message_count": 2,
            "last_user_message": "Does CATL conform to the concept of value investing?",
            "report_refs": [],
            "current_summary": {
                "abstract": "Okay, the data is complete. Below I use**The classic framework of value investing**Let s dismantle the Ningde era layer by layer.\n\n---\n\n## 🔍 Ningde era × Value investment physical examination",
                "confirmed_facts": [],
                "open_questions": [],
                "next_actions": [],
                "focus_score": 0.0,
            },
        }
    )

    assert item["current_summary"] is None


def test_store_thread_summary_memory_is_noop(monkeypatch):
    """Contract: Topic summaries are only kept in the Mongo thread collection and are no longer written to mem0 long-term memory.

     (The old test asserted that it was written to mem0, but the function was changed to no-op; retaining the test prevents the behavior from being accidentally changed back. )
    """
    called = {"count": 0}

    class DummyMemoryService:
        async def store(self, messages, **kwargs):
            called["count"] += 1
            return SimpleNamespace(facts_extracted=0, success=True, error="")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: DummyMemoryService())

    asyncio.run(
        service._store_thread_summary_memory(
            db=object(),
            user_id="user-1",
            thread_id="thr-1",
            title="Ningde era",
            summary={
                "abstract": "CATL is currently closer to a high level of shock than an extreme bubble.",
                "confirmed_facts": ["PEG still below 1"],
                "open_questions": [],
                "next_actions": [],
                "focus_score": 0.82,
            },
            summary_type="auto",
        )
    )

    assert called["count"] == 0


def _async_return(value):
    async def _inner(*args, **kwargs):
        return value

    return _inner


class TestSummaryTranscriptBudget:
    def test_total_budget_caps_length_and_keeps_latest(self):
        """The total amount is capped at 6,000 characters. When the budget is exceeded, the latest messages will be retained (old messages will be discarded)"""
        messages = (
            [{"role": "user", "content": "old question" + "A" * 700}]
            + [
                {"role": "assistant", "content": f"No.{i}Replies" + "B" * 700}
                for i in range(9)
            ]
            + [{"role": "user", "content": "Latest questions" + "C" * 700}]
        )  # 11 articles in total, each article 700+ characters, totaling well over 6000

        text = service._format_messages_for_summary(messages)

        assert len(text) <= 6100  # Allow small overhead for number/role prefixes
        assert "Latest questions" in text
        assert "old question" not in text  # The oldest news is squeezed out of the budget

    def test_short_conversation_kept_intact(self):
        messages = [
            {"role": "user", "content": "Ask about recent sales"},
            {"role": "assistant", "content": "M9 Monthly sales exceed 10,000"},
        ]
        text = service._format_messages_for_summary(messages)
        assert "Ask about recent sales" in text
        assert "M9 Monthly sales exceed 10,000" in text
        # Numbered in chronological order
        assert text.index("1. [user]") < text.index("2. [assistant]")

    def test_empty_content_skipped(self):
        messages = [
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "There is content"},
        ]
        text = service._format_messages_for_summary(messages)
        assert "There is content" in text


class TestSaveAssistantMessageSummaryScheduling:
    def test_summary_runs_in_background_without_blocking_save(self, monkeypatch):
        """The message is synchronized and dropped into the database, and the summary fire-and-forget:save has not yet been executed when returning.
        Execute in the background after leaving the event loop."""
        appended = []

        async def fake_append(db, *, user_id, role, content, conversation_id=None, **kw):
            appended.append(role)
            return "thr-bg-1"

        summary_started = asyncio.Event()
        summary_done = asyncio.Event()

        async def fake_summarize(db, user_id, conversation_id=None, summary_type="manual"):
            summary_started.set()
            # Simulating the LLM summary is time consuming; the critical path should not wait for it
            await asyncio.sleep(0.05)
            summary_done.set()

        monkeypatch.setattr(service, "append_assistant_message", fake_append)
        monkeypatch.setattr(service, "summarize_assistant_thread", fake_summarize)

        async def scenario():
            await service.save_assistant_message(
                db=object(),
                user_id="u1",
                user_content="Ask about sales volume",
                assistant_content="M9 Over ten thousand",
                tools_used=["dongchedi_x"],
                conversation_id=None,
            )
            # save Returned: Two messages are dropped into the database simultaneously……
            assert appended == ["user", "assistant"]
            # ……But the digest is still being queued/executed in the background (save is not blocked)
            assert not summary_done.is_set()
            # Wait for the background task to finish
            await asyncio.wait_for(summary_done.wait(), timeout=2)
            assert summary_started.is_set()

        asyncio.run(scenario())


def _fake_llm_config() -> LLMConfig:
    return LLMConfig(
        provider=LLMProvider.DASHSCOPE,
        model="summary-test-model",
        api_key="test-key",
        base_url="https://example.test/v1",
        max_tokens=1024,
        timeout=60,
    )