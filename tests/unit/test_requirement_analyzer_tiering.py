# -*- coding: utf-8 -*-
"""Requirements dialogue model grading and fallback logic testing.

Background: Clarity assessment/boundary detection/multiple rounds of dialogue responses/specification generation in the Skill requirements communication stage
Originally all adopted the deep reasoning model (thinking type, single minute level), resulting in the first round of response 20+ minutes,
Specification preview 10+ minutes. After grading: Prioritize fast in the light reasoning process (dialogue reply/specification generation)
Model, fall back to the main model when the fast model is unavailable; skip twice when detecting non-field-level empirical facts
Specification generation (external_api mode reconnaissance does not detect external interfaces, and there is no increment in secondary generation).
"""
import asyncio
import json
from types import SimpleNamespace

from core.llm import Message
from core.tools.external.requirement_analyzer import (
    ClarityLevel,
    RequirementAnalyzer,
)
from core.tools.external.skill_spec import (
    ImplementationFactReport,
    ImplementationHelper,
    SkillSpec,
)


class _FakeClient:
    """Fake LLM client that records the number of calls"""

    def __init__(self, content: str = "ok", raise_exc: Exception | None = None):
        self._content = content
        self._raise = raise_exc
        self.calls = 0

    def chat(self, messages):
        self.calls += 1
        if self._raise:
            raise self._raise
        return SimpleNamespace(content=self._content)


def _analyzer(main=None, quick=None) -> RequirementAnalyzer:
    return RequirementAnalyzer(
        llm_client=main if main is not None else _FakeClient("main-reply"),
        quick_llm_client=quick,
    )


# ---------- _chat_with_quick_fallback ----------

def test_quick_fallback_uses_quick_when_ok():
    quick, main = _FakeClient("quick-reply"), _FakeClient("main-reply")
    analyzer = _analyzer(main, quick)

    out = analyzer._chat_with_quick_fallback(
        [Message(role="user", content="hi")], stage="test"
    )

    assert out == "quick-reply"
    assert quick.calls == 1
    assert main.calls == 0


def test_quick_fallback_on_exception():
    quick = _FakeClient(raise_exc=RuntimeError("Error code: 403 - AccountOverdueError"))
    main = _FakeClient("main-reply")
    analyzer = _analyzer(main, quick)

    out = analyzer._chat_with_quick_fallback(
        [Message(role="user", content="hi")], stage="test"
    )

    assert out == "main-reply"
    assert main.calls == 1


def test_quick_fallback_on_empty_content():
    quick, main = _FakeClient("   "), _FakeClient("main-reply")
    analyzer = _analyzer(main, quick)

    out = analyzer._chat_with_quick_fallback(
        [Message(role="user", content="hi")], stage="test"
    )

    assert out == "main-reply"
    assert main.calls == 1


def test_quick_fallback_without_quick_client():
    main = _FakeClient("main-reply")
    analyzer = _analyzer(main, quick=None)

    assert analyzer._get_quick_client() is None
    out = analyzer._chat_with_quick_fallback(
        [Message(role="user", content="hi")], stage="test"
    )

    assert out == "main-reply"
    assert main.calls == 1


# ---------- Easily determine routing ----------

def test_assess_clarity_uses_quick_model():
    quick, main = _FakeClient("5"), _FakeClient("3")
    analyzer = _analyzer(main, quick)

    level = analyzer._assess_clarity("Obtain monthly sales data from Dianchedi")

    assert level == ClarityLevel.HIGH
    assert quick.calls == 1
    assert main.calls == 0


def test_assess_clarity_degrades_to_medium_on_quick_failure():
    quick = _FakeClient(raise_exc=RuntimeError("Error code: 403"))
    main = _FakeClient("3")
    analyzer = _analyzer(main, quick)

    level = analyzer._assess_clarity("Get data")

    # When the fast model fails, it is quickly downgraded to MEDIUM without rolling back the main model (avoiding waiting for several minutes)
    assert level == ClarityLevel.MEDIUM
    assert main.calls == 0


def test_check_boundary_uses_quick_model():
    quick = _FakeClient(
        '{"within_boundary": true, "complexity_score": 1,'
        ' "concerns": [], "decomposition_suggestions": []}'
    )
    main = _FakeClient("{}")
    analyzer = _analyzer(main, quick)

    check = analyzer._check_boundary("Get the sales volume of the car expert")

    assert check.within_boundary is True
    assert quick.calls == 1
    assert main.calls == 0


# ---------- Conversation reply routing ----------

def test_round1_response_uses_quick_model():
    quick, main = _FakeClient("Round 1 Quick Reply"), _FakeClient("Round 1 main model reply")
    analyzer = _analyzer(main, quick)
    session = analyzer.create_session()

    out = analyzer._build_round1_response(session, "Get the monthly sales volume of the car dealer")

    assert out == "Round 1 Quick Reply"
    assert quick.calls == 1
    assert main.calls == 0


def test_round1_response_falls_back_to_main():
    quick = _FakeClient(raise_exc=TimeoutError("Request timed out."))
    main = _FakeClient("Round 1 main model reply")
    analyzer = _analyzer(main, quick)
    session = analyzer.create_session()

    out = analyzer._build_round1_response(session, "Get the monthly sales volume of the car dealer")

    assert out == "Round 1 main model reply"
    assert quick.calls == 1
    assert main.calls == 1


def test_spec_confirmation_uses_quick_model():
    quick, main = _FakeClient("Specification confirmation quick reply"), _FakeClient("master model")
    analyzer = _analyzer(main, quick)
    session = analyzer.create_session()

    out = analyzer._build_spec_confirmation(session, "Confirm")

    assert out == "Specification confirmation quick reply"
    assert quick.calls == 1
    assert main.calls == 0


# ---------- Specification generation route ----------

_SPEC_JSON = json.dumps({
    "tool_id": "get_dongchedi_sales",
    "display_name": "Understand car sales",
    "description": "Get the monthly sales volume of car models",
    "category": "utility",
    "data_source": "dongchedi",
    "parameters": [],
    "expected_output": {
        "type": "list[dict]", "fields": ["rank", "model_name"], "description": "sales list",
    },
    "validation_checks": [],
    "constraints": [],
    "test_input": {},
}, ensure_ascii=False)


def test_generate_spec_uses_quick_model():
    quick, main = _FakeClient(_SPEC_JSON), _FakeClient(_SPEC_JSON)
    analyzer = _analyzer(main, quick)

    spec = analyzer._generate_spec("The user wants to obtain the monthly sales data of Qianchedi")

    assert spec is not None
    assert spec.tool_id == "get_dongchedi_sales"
    assert quick.calls == 1
    assert main.calls == 0


def test_generate_spec_falls_back_to_main_on_quick_failure():
    quick = _FakeClient(raise_exc=RuntimeError("Error code: 403 - AccountOverdueError"))
    main = _FakeClient(_SPEC_JSON)
    analyzer = _analyzer(main, quick)

    spec = analyzer._generate_spec("The user wants to obtain the monthly sales data of Qianchedi")

    assert spec is not None
    assert spec.tool_id == "get_dongchedi_sales"
    assert main.calls == 1


# ---------- Reconnaissance fact judgment and secondary generation skipping ----------

def test_fact_report_grounding_flag():
    assert ImplementationFactReport().has_spec_grounding_facts is False
    report = ImplementationFactReport(
        available_helpers=[ImplementationHelper(name="get_stock_news")]
    )
    assert report.has_spec_grounding_facts is True


class _StubAnalyzer:
    """Stub that records preview_spec calls (including fact_report input parameters)"""

    def __init__(self, spec):
        self._spec = spec
        self.preview_calls = []

    def preview_spec(self, session, user_message, fact_report=None, parent_contract=None):
        self.preview_calls.append(fact_report)
        return self._spec


class _StubRecon:
    def __init__(self, report):
        self._report = report

    def analyze(self, spec, capability_hits):
        return self._report


def _make_preview_service(draft_spec, fact_report):
    """Construct a service that only mounts the preview_spec dependency stub (bypassing the heavyweight constructor)"""
    from app.services.skill_generation_service import SkillGenerationService

    service = SkillGenerationService.__new__(SkillGenerationService)
    stub = _StubAnalyzer(draft_spec)
    service._analyzer = stub
    service._reconnaissance = _StubRecon(fact_report)

    session = RequirementAnalyzer().create_session()

    async def _load(session_id):
        return session

    async def _save(s):
        pass

    async def _search(spec):
        return []

    service._load_session = _load
    service._save_session = _save
    service._search_capability_index = _search
    service._apply_handoff_context_to_spec = lambda spec, ctx: None
    service._build_session_recommendations = lambda **kw: {}
    return service, stub


def test_preview_spec_skips_second_pass_in_external_mode():
    draft = SkillSpec(
        tool_id="get_dongchedi_sales",
        display_name="Understand car sales",
        description="Obtain the monthly sales volume of Dianchedi models through the public interface",
        data_source="dongchedi",
    )
    # Even if the report has a helper entry, external_api mode recon does not detect external interfaces and should be skipped
    report = ImplementationFactReport(
        available_helpers=[ImplementationHelper(name="x")],
        recommended_strategy="External API integration",
        confidence=0.45,
    )
    service, stub = _make_preview_service(draft, report)

    result = asyncio.run(service.preview_spec("s1", "Confirm"))

    assert len(stub.preview_calls) == 1
    assert stub.preview_calls[0] is None  # No drafts fact_report
    assert result["spec"]["tool_id"] == "get_dongchedi_sales"


def test_preview_spec_runs_second_pass_with_grounding_facts():
    draft = SkillSpec(
        tool_id="get_stock_news",
        display_name="individual stock news",
        description="Get a list of individual stock news",
        data_source="akshare",
    )
    report = ImplementationFactReport(
        available_helpers=[ImplementationHelper(name="get_stock_news")]
    )
    service, stub = _make_preview_service(draft, report)

    asyncio.run(service.preview_spec("s1", "Confirm"))

    assert len(stub.preview_calls) == 2
    assert stub.preview_calls[1] is report


def test_preview_spec_skips_second_pass_without_grounding_facts():
    draft = SkillSpec(
        tool_id="get_stock_news",
        display_name="individual stock news",
        description="Get a list of individual stock news",
        data_source="akshare",
    )
    report = ImplementationFactReport(recommended_strategy="Local collection is preferred", confidence=0.3)
    service, stub = _make_preview_service(draft, report)

    asyncio.run(service.preview_spec("s1", "Confirm"))

    assert len(stub.preview_calls) == 1
