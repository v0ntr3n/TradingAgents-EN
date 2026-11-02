# -*- coding: utf-8 -*-
"""A11 Intelligent Assistant Quality Architecture —— Phase 0 regression test set.

Corresponding design documents §5.1 10 historical pitfall cases. This document covers**not dependent on truth LLM / DB**, 
Parts that can be solidified at the pure unit level (path contracts, four lines of defense, degradation, data references);
Cases involving real LLM behavior (three perspectives: compliance rhetoric, bare digital rewriting, pre-inspection process, and risk debate)
It belongs to the integration/manual verification layer and is marked separately in the design document.

Run:env/Scripts/python -m pytest tests/unit/test_assistant_quality.py -v
"""

import asyncio

import pytest

from core.assistant import (
    EVIDENCE_HISTORY_TOOL,
    EVIDENCE_MEMORY,
    EVIDENCE_SEARCH,
    EVIDENCE_TOOL,
    EVIDENCE_USER_MESSAGE,
    REGISTERED_PASSTHROUGH,
    ROUTE_TYPE_PASSTHROUGH,
    Evidence,
    ReplyCandidate,
    ReplyGate,
    extract_data_refs,
)
from core.assistant.reply_gate import build_fallback_candidate
from core.assistant.paths import (
    AssistantRequest,
    PathRegistry,
    PRIORITY_HITL,
    PRIORITY_UNSUPPORTED_ASSET,
    PRIORITY_FAST_SEARCH,
    PRIORITY_DATA_PRECHECK,
    PRIORITY_MAIN_LLM,
    ROUTE_HITL,
    ROUTE_FAST_SEARCH,
    ROUTE_MAIN_LLM,
)
from core.assistant.lexicon import (
    StockDirectory,
    detect_unsupported_asset,
    extract_a_share_code,
)
from core.assistant.metrics import AssistantQualityMetrics


@pytest.fixture
def gate():
    return ReplyGate()


def _ev(source_type, source_id, content, locator=None):
    return Evidence(source_type=source_type, source_id=source_id, content=content, locator=locator)


# ─────────────────────────── Path type contract (governing Class B naked passthrough)───────────────────────────

class TestRouteContract:
    def test_clean_answer_passes(self, gate):
        c = ReplyCandidate.answer("This is an analyzed answer.", "main_llm", llm_processed=True)
        r = gate.run(c, "question")
        assert r.passed, r.failures

    def test_answer_without_llm_blocked(self, gate):
        """Case 1: If the fast path returns directly without LLM, the contract layer must intercept it (without relying on text heuristics)."""
        c = ReplyCandidate.answer("List of ten naked search title links……", "fast_search", llm_processed=False)
        r = gate.run(c, "What new cars has Cyrus launched recently?")
        assert not r.passed
        assert "llm_processed_contract" in r.failed_checks

    def test_registered_passthrough_passes(self, gate):
        for route_id in ("hitl", "unsupported_asset", "data_precheck",
                         "llm_unavailable", "timeout", "error", "fallback_evidence"):
            assert route_id in REGISTERED_PASSTHROUGH
            c = ReplyCandidate.passthrough("System prompt", route_id)
            assert gate.run(c).passed, route_id

    def test_unregistered_passthrough_blocked(self, gate):
        c = ReplyCandidate.passthrough("Secretly come out", "rogue_new_bypass")
        r = gate.run(c)
        assert not r.passed
        assert "passthrough_registration" in r.failed_checks

    def test_answer_requires_explicit_llm_flag(self):
        """answer The factory must pass llm_processed, and it is forbidden to treat LLM as passed by default."""
        with pytest.raises(TypeError):
            ReplyCandidate.answer("x", "main_llm")  # type: ignore[call-arg]


# ─────────────────────────── A Category: Four lines of defense for digital/trace traceability ───────────────────────────

class TestFabricationDefenses:
    def test_unsourced_numbers_blocked(self, gate):
        """Case 7: Stacking a lot of precise numbers without adjusting any tools → Interception."""
        reply = "The company has revenue of 100 million yuan, net profit of 200 million yuan, sales of 30,000 vehicles, cost of 4 yuan, growth of 5%, debt ratio of 6%, and gross profit of 700 million yuan."
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True, tools_used=[]
        )
        r = gate.run(c, "How is this company doing?")
        assert not r.passed
        assert "unsourced_numbers" in r.failed_checks

    def test_fabricated_tool_json_blocked(self, gate):
        reply = 'get_stock_data(600519) → {"price": 1688.0, "pe": 25.3} This is the tool result'
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["get_stock_data"],
            evidence=[_ev(EVIDENCE_TOOL, "get_stock_data", "The actual return is Markdown text")],
        )
        r = gate.run(c, "Check it out")
        assert not r.passed
        assert "fabricated_tool_json" in r.failed_checks

    def test_fabricated_tool_ref_blocked(self, gate):
        reply = "Data source: get_fake_nonexistent_tool, showing market share of 30%."
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["some_other_tool"],
        )
        r = gate.run(c, "Market share")
        assert not r.passed
        assert "fabricated_tool_refs" in r.failed_checks

    def test_untraced_risky_numbers_blocked(self, gate):
        """Case 3: The tool was adjusted, but the tool did not have any numbers, but the reply contained 6 high-risk numbers. → Interception."""
        reply = ("The valuations are respectively 1.11 billion yuan, 2.22 billion yuan, 3.33 billion yuan,"
                 "44.4 billion, 5.55 billion yuan, 6.66 billion yuan.")
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["get_x"],
            evidence=[_ev(EVIDENCE_TOOL, "get_x", "Tool return: Recent announcements are mainly qualitative descriptions.")],
        )
        r = gate.run(c, "How much is the valuation?")
        assert not r.passed
        assert "untraced_risky_numbers" in r.failed_checks

    def test_number_traceable_to_tool_passes(self, gate):
        """The reply number can be traced back to the source in the tool return → Release."""
        content = "Cyrus neutral scenario target price is 46.28 yuan, corresponding to a market value of 80.62 billion yuan."
        reply = "According to tool calculations, the neutral scenario target price is 46.28 yuan."
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["get_valuation"],
            evidence=[_ev(EVIDENCE_TOOL, "get_valuation", content)],
        )
        r = gate.run(c, "target price")
        assert r.passed, r.failures

    def test_number_traceable_to_history_passes(self, gate):
        """Case 8: Multiple rounds of quoting figures from the previous round of tools should not be misjudged as fabrication."""
        reply = "The last round of tools showed a target price of 69.14 yuan, and this conclusion will be adopted in this round."
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["get_valuation"],
            evidence=[
                _ev(EVIDENCE_TOOL, "get_valuation", "Only text descriptions are returned in this round."),
                _ev(EVIDENCE_HISTORY_TOOL, "get_valuation", "Historical tool results: Optimistic target price of 69.14 yuan"),
            ],
        )
        r = gate.run(c, "continue")
        assert r.passed, r.failures

    def test_number_traceable_to_memory_passes(self, gate):
        """References to injected factual memory numbers should not be misjudged."""
        reply = "According to previous records, the complete cost of the industry is about 15.8 yuan/kg."
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["ask"],
            evidence=[
                _ev(EVIDENCE_TOOL, "ask", "OK."),
                _ev(EVIDENCE_MEMORY, "mem0", "The complete cost of the industry is about 15.8 yuan/kg (collected recently)"),
            ],
        )
        r = gate.run(c, "How much does it cost")
        assert r.passed, r.failures

    def test_number_from_user_message_passes(self, gate):
        """Numbers given by users themselves and quoted by assistants are not considered fabricated."""
        c = ReplyCandidate.answer(
            reply="The cost of 12.3 yuan/kg you mentioned has been recorded, based on this……",
            route_id="main_llm", llm_processed=True, tools_used=["chat"],
            evidence=[_ev(EVIDENCE_TOOL, "chat", "Okay, let me analyze it.")],
        )
        r = gate.run(c, "What if the cost is 12.3 yuan/kg?")
        assert r.passed, r.failures

    def test_valuation_excel_verbatim_presentation_passes(self, gate):
        """Case 2: Valuation Excel tool results are required to be presented as they are (including numbers)+download link),
        answer It can be passed without any exemption under the type contract (all numbers are traceable, no JSON forgery)."""
        content = (
            "Valuation estimate generated:\n"
            "| Scenario | Target price (yuan) |\n|---|---|\n"
            "| pessimistic | 29.01 |\n| Neutral | 40.61 |\n| optimistic | 69.14 |\n"
            "Download:/api/assistant/deliverables/valuation_601127.xlsx"
        )
        reply = content  # LLM Presented as is by instrument contract
        c = ReplyCandidate.answer(
            reply, "main_llm", llm_processed=True,
            tools_used=["generate_valuation_excel_tool"],
            evidence=[_ev(EVIDENCE_TOOL, "generate_valuation_excel_tool", content,
                          locator="/api/assistant/deliverables/valuation_601127.xlsx")],
        )
        r = gate.run(c, "Generate valuation table")
        assert r.passed, r.failures


# ─────────────────────────── Two-Level Downgrade: Fallback Evidence ───────────────────────────

class TestFallback:
    def test_contract_failure_degrades_to_registered_evidence(self, gate):
        raw = "Search engine: ten titles and links (no text)……" * 3
        c = ReplyCandidate.answer(
            raw, "fast_search", llm_processed=False,
            tools_used=["search_recent_information"],
            evidence=[_ev(EVIDENCE_SEARCH, "search_recent_information", raw)],
        )
        result = gate.run(c, "What new cars are there recently?")
        assert not result.passed

        fb = build_fallback_candidate(c, result.failures)
        assert fb.route_id == "fallback_evidence"
        assert fb.route_type == "passthrough_allowed"
        assert fb.route_id in REGISTERED_PASSTHROUGH
        # The downgrade reply is not a bare list: it contains a description of limitations and is accompanied by authentic data sources.
        assert "Data quality check" in fb.reply
        assert "search_recent_information" in fb.reply
        # The downgraded product itself is legal and can pass the gate (whitelist)
        assert gate.run(fb).passed

    def test_fallback_without_evidence_is_honest(self, gate):
        c = ReplyCandidate.answer(
            "answer", "main_llm", llm_processed=False, tools_used=[], evidence=[]
        )
        result = gate.run(c, "question")
        fb = build_fallback_candidate(c, result.failures)
        assert "No citationable original data was obtained" in fb.reply


# ─────────────────────────── Path registry (S5 explicit priority / S1 not bypassable)───────────────────────────

class TestPathRegistry:
    @staticmethod
    def _req():
        return AssistantRequest(service=None, user_message="question")

    @pytest.mark.asyncio
    async def test_resolve_picks_first_match_by_priority(self):
        calls = []

        async def hitl_handler(req):
            calls.append(ROUTE_HITL)
            return None

        async def fast_handler(req):
            calls.append(ROUTE_FAST_SEARCH)
            return None

        async def main_handler(req):
            calls.append(ROUTE_MAIN_LLM)
            return ReplyCandidate.answer("main path", ROUTE_MAIN_LLM, llm_processed=True)

        registry = PathRegistry()
        registry.register(ROUTE_HITL, PRIORITY_HITL, hitl_handler,
                          route_type=ROUTE_TYPE_PASSTHROUGH)
        registry.register(ROUTE_FAST_SEARCH, PRIORITY_FAST_SEARCH, fast_handler)
        registry.register(ROUTE_MAIN_LLM, PRIORITY_MAIN_LLM, main_handler)

        cand = await registry.resolve(self._req())
        assert cand.route_id == ROUTE_MAIN_LLM
        assert calls == [ROUTE_HITL, ROUTE_FAST_SEARCH, ROUTE_MAIN_LLM]  # Strictly based on priority
        assert cand.meta["route_priority"] == PRIORITY_MAIN_LLM

    @pytest.mark.asyncio
    async def test_higher_priority_match_short_circuits(self):
        async def hitl(req):
            return ReplyCandidate.passthrough("Confirmed", ROUTE_HITL)

        async def forbidden_main(req):
            raise AssertionError("HITL The main path should no longer be executed after the hit")

        registry = PathRegistry()
        registry.register(ROUTE_HITL, PRIORITY_HITL, hitl,
                          route_type=ROUTE_TYPE_PASSTHROUGH)
        registry.register(ROUTE_MAIN_LLM, PRIORITY_MAIN_LLM, forbidden_main)

        cand = await registry.resolve(self._req())
        assert cand.route_id == ROUTE_HITL
        assert cand.meta["route_priority"] == PRIORITY_HITL

    def test_priority_order_matches_legacy_precedence(self):
        """fast path(40) Must be preceded by data pre-check(50)——Keep before refactoring chat() actual behavior."""
        assert PRIORITY_HITL < PRIORITY_UNSUPPORTED_ASSET
        assert PRIORITY_UNSUPPORTED_ASSET < PRIORITY_FAST_SEARCH
        assert PRIORITY_FAST_SEARCH < PRIORITY_DATA_PRECHECK
        assert PRIORITY_DATA_PRECHECK < PRIORITY_MAIN_LLM

    def test_duplicate_route_rejected(self):
        async def h(req):
            return None

        registry = PathRegistry().register(ROUTE_FAST_SEARCH, PRIORITY_FAST_SEARCH, h)
        with pytest.raises(ValueError):
            registry.register(ROUTE_FAST_SEARCH, PRIORITY_FAST_SEARCH + 1, h)

    @pytest.mark.asyncio
    async def test_no_match_raises(self):
        async def none_path(req):
            return None

        registry = PathRegistry().register("x", 1, none_path)
        with pytest.raises(RuntimeError):
            await registry.resolve(self._req())


# ─────────────────────────── data_refs Really come true ───────────────────────────

class TestDataRefs:
    def test_only_tool_and_search_presented_dedup(self):
        evidence = [
            _ev(EVIDENCE_TOOL, "get_a", "content 1"),
            _ev(EVIDENCE_TOOL, "get_a", "Content 1 is repeated"),                # Remove duplicates
            _ev(EVIDENCE_SEARCH, "searxng", "content 2", locator="http://x"),
            _ev(EVIDENCE_USER_MESSAGE, "user", "User s words"),          # Do not display
            _ev(EVIDENCE_MEMORY, "mem0", "memory"),                    # Do not display
            _ev(EVIDENCE_HISTORY_TOOL, "get_old", "history"),           # Do not display
        ]
        refs = extract_data_refs(evidence)
        assert len(refs) == 2
        kinds = {(r["source_type"], r["source_id"]) for r in refs}
        assert kinds == {("tool", "get_a"), ("search", "searxng")}
        search_ref = next(r for r in refs if r["source_type"] == "search")
        assert search_ref["locator"] == "http://x"

    def test_empty_evidence_returns_empty_refs(self):
        assert extract_data_refs(None) == []
        assert extract_data_refs([]) == []


# ─────────────────────────── Dictionary fact source (Phase 4: lexicon)───────────────────────────

class TestAShareCodeExtraction:
    def test_extract_from_plain_text(self):
        assert extract_a_share_code("600519 What is the current valuation?") == "600519"
        # \b No boundary between Chinese and numbers (consistent with historical _STOCK_CODE_RE behavior), whitespace/punctuation separation required
        assert extract_a_share_code("Help me analyze it 000858") == "000858"
        assert extract_a_share_code("300750 Which one is better between 601127 and 601127?") == "300750"  # first hit

    def test_no_code_returns_none(self):
        assert extract_a_share_code("") is None
        assert extract_a_share_code(None) is None  # type: ignore[arg-type]
        assert extract_a_share_code("Analyze Kweichow Moutai") is None

    def test_word_boundaries_reject_longer_digits(self):
        """7 digit strings should not truncate the 6-digit code (\\b Boundaries are consistent with historical behavior)."""
        assert extract_a_share_code("Please check order number 3007501") is None


class TestUnsupportedAssetGate:
    """Variety gate detection (service and planned share the same fact source, and the vocabulary behavior is verified here)."""

    def test_hk_keyword_hits_hk_message(self):
        msg = detect_unsupported_asset("How is Tencent Holdings doing lately?")
        assert msg is not None
        assert "Hong Kong stocks" in msg

    def test_us_keyword_hits_us_message(self):
        msg = detect_unsupported_asset("Can I still buy a Tesla?")
        assert msg is not None
        assert "US stocks" in msg

    def test_us_ticker_hits_us_code_message(self):
        msg = detect_unsupported_asset("TSLA How much is it now?")
        assert msg is not None
        assert "US stock code" in msg

    def test_hk_code_hits_hk_code_message(self):
        msg = detect_unsupported_asset("00700.HK Is it worth paying attention to?")
        assert msg is not None
        assert "Hong Kong stock code" in msg

    def test_a_share_question_not_blocked(self):
        assert detect_unsupported_asset("Analyze 600519 Moutai") is None
        assert detect_unsupported_asset("") is None
        assert detect_unsupported_asset(None) is None  # type: ignore[arg-type]

    def test_hk_takes_precedence_over_us(self):
        """Historical behavior: Hong Kong stock terms are detected before US stock terms."""
        msg = detect_unsupported_asset("Which is better, Hong Kong stocks or US stocks?")
        assert msg is not None
        assert "Hong Kong stocks" in msg


class _FakeCursor:
    """Minimal asynchronous cursor stub: supports async for."""

    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


class _FakeCollection:
    def __init__(self, docs, fail=False):
        self._docs = docs
        self._fail = fail
        self.find_calls = 0

    def find(self, *args, **kwargs):
        self.find_calls += 1
        if self._fail:
            raise RuntimeError("Database is temporarily unavailable")
        return _FakeCursor(self._docs)


class _FakeDB:
    def __init__(self, docs, fail=False):
        self.stock_basic_info = _FakeCollection(docs, fail=fail)

    def __getitem__(self, name):
        assert name == "stock_basic_info"
        return self.stock_basic_info


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _basic_docs():
    return [
        {"symbol": "600519", "name": "Kweichow Moutai"},
        {"symbol": "601127", "name": "Thalys Group"},
        {"symbol": "688777", "name": "Thalys"},
        {"symbol": "000001", "name": "Ping An Bank"},
        {"symbol": "999999", "name": "super"},                        # 1 Word names should be filtered
        {"symbol": "888888", "name": "This is a name with more than six words"},   # >6 word filter
        {"symbol": "111111", "name": "Duplication of the same name"},                  # Names reserved come first
        {"symbol": "222222", "name": "Duplication of the same name"},
    ]


class TestStockDirectory:
    @pytest.mark.asyncio
    async def test_full_load_with_name_filter(self):
        clock = _FakeClock()
        directory = StockDirectory(ttl_seconds=3600, clock=clock)
        name_map = await directory.get_name_map(_FakeDB(_basic_docs()))
        # Full load:2~6 All character names are stored in the database, and 1 character/extremely long names are filtered.
        assert name_map["Kweichow Moutai"] == "600519"
        assert name_map["Thalys"] == "688777"
        assert "super" not in name_map
        assert "This is a name with more than six words" not in name_map
        assert name_map["Duplication of the same name"] == "111111"  # Keep the code that appears first with the same name

    @pytest.mark.asyncio
    async def test_ttl_cache_avoids_second_query(self):
        clock = _FakeClock()
        db = _FakeDB(_basic_docs())
        directory = StockDirectory(ttl_seconds=3600, clock=clock)
        await directory.get_name_map(db)
        clock.now += 1800  # TTL within
        await directory.get_name_map(db)
        assert db.stock_basic_info.find_calls == 1  # TTL Internal zero query

    @pytest.mark.asyncio
    async def test_expired_ttl_triggers_refresh(self):
        clock = _FakeClock()
        db = _FakeDB(_basic_docs())
        directory = StockDirectory(ttl_seconds=3600, clock=clock)
        await directory.get_name_map(db)
        clock.now += 3601  # Expired
        await directory.get_name_map(db)
        assert db.stock_basic_info.find_calls == 2

    @pytest.mark.asyncio
    async def test_refresh_failure_keeps_old_cache(self):
        """If the refresh fails, the old cache will be used.——Dictionary failure does not block routing."""
        clock = _FakeClock()
        db = _FakeDB(_basic_docs())
        directory = StockDirectory(ttl_seconds=3600, clock=clock)
        await directory.get_name_map(db)
        db.stock_basic_info._fail = True
        clock.now += 3601
        name_map = await directory.get_name_map(db)
        assert name_map["Kweichow Moutai"] == "600519"  # Old data is still available
        assert directory.is_fresh()  # The timestamp will also be refreshed on failure to avoid retrying the database for each request.

    @pytest.mark.asyncio
    async def test_resolve_prefers_code_then_longest_name(self):
        db = _FakeDB(_basic_docs())
        directory = StockDirectory(ttl_seconds=3600, clock=_FakeClock())
        assert await directory.resolve_symbol("600519 valuation", db) == "600519"  # code first
        assert await directory.resolve_symbol("Thalys Group s performance", db) == "601127"  # Long names are preferred
        assert await directory.resolve_symbol("How about Cyrus", db) == "688777"
        assert await directory.resolve_symbol("Completely irrelevant chat content", db) is None


# ─────────────────────────── Quality focus (stage 4: metrics)───────────────────────────

class _MetricsColl:
    def __init__(self, fail=False):
        self.inserted = []
        self._fail = fail

    async def insert_one(self, doc):
        if self._fail:
            raise RuntimeError("boom")
        self.inserted.append(doc)

    async def create_index(self, *args, **kwargs):
        return None


class _MetricsDB:
    def __init__(self, fail=False):
        self.events = _MetricsColl(fail=fail)

    def __getitem__(self, name):
        assert name == "assistant_quality_events"
        return self.events


class TestQualityMetrics:
    def test_record_without_loop_drops_silently(self):
        """Synchronization context (no event loop) is silently discarded——Buried points cannot block the main link."""
        db = _MetricsDB()
        AssistantQualityMetrics().record(db=db, route_id="main_llm")  # No exception should be thrown
        assert db.events.inserted == []

    @pytest.mark.asyncio
    async def test_record_persists_event(self):
        db = _MetricsDB()
        metrics = AssistantQualityMetrics()
        metrics.record(db=db, route_id="main_llm", streaming=False,
                       gate_passed=True, quality_signals=["fabricated_json"])
        await asyncio.sleep(0.01)  # Let the fire-and-forget task execute
        assert len(db.events.inserted) == 1
        event = db.events.inserted[0]
        assert event["route_id"] == "main_llm"
        assert event["quality_signals"] == ["fabricated_json"]
        assert event["created_at"] is not None

    @pytest.mark.asyncio
    async def test_insert_failure_never_raises(self):
        db = _MetricsDB(fail=True)
        AssistantQualityMetrics().record(db=db, route_id="x")
        await asyncio.sleep(0.01)  # Exceptions are swallowed internally within the task and are not propagated outwards.
        assert db.events.inserted == []

    @pytest.mark.asyncio
    async def test_record_without_db_drops(self):
        """There is an event loop but no db handle → Discard silently."""
        AssistantQualityMetrics().record(db=None, route_id="x")  # No exception should be thrown
