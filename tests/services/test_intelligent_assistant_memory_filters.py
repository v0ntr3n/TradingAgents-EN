import pytest

from app.services.intelligent_assistant_service import (
    _extract_memory_metadata_filters,
    _recall_memory_block,
)


class _FakeMemoryService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def recall_formatted(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _FakeProjectMemoryService:
    def __init__(self, response: str):
        self.response = response
        self.calls = []

    async def build_prompt_block(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_extract_memory_metadata_filters_reads_symbol_from_topic_title() -> None:
    assert _extract_memory_metadata_filters("Kweichow Moutai(600519) analysis report") == {"symbol": "600519"}
    assert _extract_memory_metadata_filters("Tencent Holdings(HK.00700) analysis report") == {"symbol": "HK.00700"}
    assert _extract_memory_metadata_filters("Macro strategy discussion") is None


def test_extract_memory_metadata_filters_falls_back_to_report_refs() -> None:
    assert _extract_memory_metadata_filters(
        "Macro strategy discussion",
        report_refs=[{"symbol": "sz.000001"}, {"symbol": "600519"}],
    ) == {"symbol": "SZ.000001"}


@pytest.mark.asyncio
async def test_recall_memory_block_passes_symbol_metadata_filters(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    result = await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="Help me review the previous analysis conclusions of this target.",
        current_topic_title="Kweichow Moutai(600519) analysis report",
    )

    assert result == "memory block"
    assert len(fake_memory_service.calls) == 1
    call = fake_memory_service.calls[0]
    assert call["metadata_filters"] == {"symbol": "600519"}
    assert call["scopes"] == ["conversation", "user_preference", "analysis_insight", "trade_pattern"]


@pytest.mark.asyncio
async def test_recall_memory_block_skips_metadata_filters_without_symbol(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="To summarize my recent preferences",
        current_topic_title="Macro strategy discussion",
    )

    assert len(fake_memory_service.calls) == 1
    assert fake_memory_service.calls[0]["metadata_filters"] is None


@pytest.mark.asyncio
async def test_recall_memory_block_uses_report_ref_symbol_when_title_has_no_symbol(monkeypatch):
    fake_memory_service = _FakeMemoryService("memory block")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)

    await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="Review historical analysis of this topic",
        current_topic_title="Macro strategy discussion",
        report_refs=[{"symbol": "hk.00700", "title": "Tencent Holdings(HK.00700) analysis report"}],
    )

    assert len(fake_memory_service.calls) == 1
    assert fake_memory_service.calls[0]["metadata_filters"] == {"symbol": "HK.00700"}


@pytest.mark.asyncio
async def test_recall_memory_block_combines_project_memory_with_mem0(monkeypatch):
    fake_memory_service = _FakeMemoryService(" [Historical preferences]\n- Prefer to read the conclusion first")
    fake_project_memory_service = _FakeProjectMemoryService(" [Project long-term memory]\n- Output constraints\n  - Answer structure: give conclusion first")

    monkeypatch.setattr("core.memory.service.get_memory_service", lambda db: fake_memory_service)
    monkeypatch.setattr(
        "app.services.project_memory_service.get_project_memory_service",
        lambda db: fake_project_memory_service,
    )

    result = await _recall_memory_block(
        db=object(),
        user_id="user-1",
        user_message="continue this theme",
        current_topic_title="Macro strategy discussion",
    )

    assert " [Project long-term memory]" in result
    assert " [Historical preferences]" in result
    assert len(fake_project_memory_service.calls) == 1
    assert fake_project_memory_service.calls[0]["max_items"] == 4