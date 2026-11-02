from __future__ import annotations

# === Merged from test_analysis_result_normalization.py ===
from app.routers.analysis import has_meaningful_result_payload, normalize_result_data


def test_normalize_result_data_preserves_full_reports_for_detail_endpoints():
	raw_market_report = "# Market technical analysis\n\n This is complete technical market analysis content and should not be compressed in the details interface.\n\n- observation point A\n- observation point B"
	raw_research_report = "# Optimistic Scenario Researcher\n\n This is the complete optimistic scenario argument and should not be filtered out."

	result = normalize_result_data(
		{
			"summary": "Full summary",
			"recommendation": "Complete research conclusion",
			"reports": {
				"market_report": raw_market_report,
				"bull_researcher": raw_research_report,
			},
		}
	)

	assert result["summary"] == "Full summary"
	assert result["recommendation"] == "Complete research conclusion"
	assert result["reports"]["market_report"] == raw_market_report
	assert result["reports"]["bull_researcher"] == raw_research_report


def test_normalize_result_data_builds_final_decision_report_when_missing():
	result = normalize_result_data(
		{
			"reports": {
				"fundamentals_report": "# fundamental analysis\n\n Here is the complete fundamental analysis."
			},
			"decision": {
				"analysis_view": "Neutral",
				"confidence": 0.75,
				"risk_score": 0.62,
				"summary": "The current situation is closer to the baseline scenario.",
				"reasoning": "The main basis comes from interest spreads, asset quality and valuation constraints.",
				"risk_warning": "It is necessary to continue to pay attention to changes in the defective rate.",
				"watch_items": ["Quarterly spread changes", "Retail overdue rate"],
			},
		}
	)

	assert "final_trade_decision" in result["reports"]
	assert "Research Judgment: Neutral" in result["reports"]["final_trade_decision"]
	assert "Mainly based on interest spread, asset quality and valuation constraints" in result["reports"]["final_trade_decision"]
	assert "Quarterly spread changes" in result["reports"]["final_trade_decision"]


def test_normalize_result_data_demotes_inferential_core_evidence_in_decision():
	result = normalize_result_data(
		{
			"decision": {
				"analysis_view": "Neutral",
				"reasoning": "It is currently more appropriate to wait for annual report disclosures.",
				"core_evidence": ["PB is 0.48 times", "The proportion of retail loans is inferred to exceed 60%"],
				"uncertainties": ["Net interest margin data is missing"],
				"watch_items": ["Next financial report"],
			},
		}
	)

	assert result["decision"]["core_evidence"] == ["PB is 0.48 times"]
	assert "The proportion of retail loans is inferred to exceed 60%" in result["decision"]["uncertainties"]


def test_has_meaningful_result_payload_rejects_empty_shell_result():
	assert has_meaningful_result_payload(
		{
			"summary": "",
			"recommendation": "",
			"reports": {},
			"decision": {},
			"key_points": [],
		}
	) is False


def test_has_meaningful_result_payload_accepts_report_backed_result():
	assert has_meaningful_result_payload(
		{
			"summary": "",
			"recommendation": "",
			"reports": {
				"market_report": "# Market technical analysis\n\n This is valid reporting content."
			},
			"decision": {},
			"key_points": [],
		}
	) is True

# === Merged from test_im_topic_digest_service.py ===
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

# === Merged from test_intelligent_screening_single_stock_query.py ===
import asyncio


def test_single_stock_high_dividend_query_short_circuits_screening_flow(monkeypatch):
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())

    async def fake_get_context_messages(user_id, conversation_id=None):
        return "conv-single-stock", []

    async def fake_fetch_single_stock_item(keyword):
        assert keyword == "Moutai"
        return {
            "code": "600519",
            "name": "Kweichow Moutai",
            "industry": "Liquor",
            "close": 1680.0,
            "dividend_yield": 3.18,
            "pe_ttm": 27.6,
            "pb": 8.5,
            "roe": 31.2,
            "report_period": "20250930",
        }

    saved = {}

    async def fake_save_message(user_id, conversation_id, user_msg, assistant_reply, tools_used, stocks, phase, is_fallback=False):
        saved["conversation_id"] = conversation_id
        saved["assistant_reply"] = assistant_reply
        saved["stocks"] = stocks
        saved["phase"] = phase

    async def fail_ensure_client():
        raise AssertionError("single-stock direct query should not require LLM client")

    monkeypatch.setattr(service, "_get_context_messages", fake_get_context_messages)
    monkeypatch.setattr(service, "_fetch_single_stock_item", fake_fetch_single_stock_item)
    monkeypatch.setattr(service, "_save_message", fake_save_message)
    monkeypatch.setattr(service, "_ensure_client", fail_ensure_client)

    result = asyncio.run(service.chat("user-1", "Is Moutai a high dividend stock?"))

    assert result["phase"] == "result"
    assert result["tools_used"] == []
    assert result["conversation_id"] == "conv-single-stock"
    assert result["stocks"][0]["code"] == "600519"
    assert result["stocks"][0]["reason"].startswith("Single stock verification")
    assert "Kweichow Moutai" in result["reply"]
    assert "Will not recommend other stocks instead" not in result["reply"]
    assert "Filter by original requirements" not in result["reply"]
    assert "Yuntianhua" not in result["reply"]
    assert saved["phase"] == "result"


def test_single_stock_judgement_detection_does_not_capture_multi_stock_screening_request():
    from app.services.intelligent_screening_service import IntelligentScreeningService

    service = IntelligentScreeningService(db=object())

    assert service._looks_like_single_stock_judgement_query("Help me choose some high dividend stocks") is False
    assert service._looks_like_single_stock_judgement_query("Is Moutai a high dividend stock?") is True

# === Merged from test_migrate_historical_manager_reports_to_mem0.py ===
import json

from app.scripts.migrate_historical_manager_reports_to_mem0 import (
    MIGRATION_SOURCE,
    REPORT_SOURCE_ANALYSIS_RESULTS,
    REPORT_SOURCE_PROGRESS_JSON,
    _build_analysis_result_record,
    _build_progress_records,
    _build_store_metadata,
)


def test_build_analysis_result_record_parses_python_literal_markdown(tmp_path):
    report_path = (
        tmp_path
        / "data"
        / "analysis_results"
        / "UNKNOWN"
        / "2025-08-20"
        / "reports"
        / "research_team_decision.md"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text(
        "{'judge_decision': '### Portfolio decision: Vanke A (000002) recommended to hold', 'history': '...'}",
        encoding="utf-8",
    )

    record = _build_analysis_result_record(report_path)

    assert record is not None
    assert record.target_agent_id == "research_manager_v2"
    assert record.source_kind == REPORT_SOURCE_ANALYSIS_RESULTS
    assert record.ticker == "000002"
    assert record.analysis_date == "2025-08-20"
    assert record.content == "### Portfolio decision: Vanke A (000002) recommended to hold"
    assert record.legacy_doc_id.endswith("data/analysis_results/UNKNOWN/2025-08-20/reports/research_team_decision.md")


def test_build_progress_records_extracts_both_manager_decisions(tmp_path):
    progress_path = tmp_path / "data" / "temp" / "processing" / "progress_analysis_demo.json"
    progress_path.parent.mkdir(parents=True)
    payload = {
        "company_of_interest": "000002",
        "trade_date": "2025-08-01",
        "investment_debate_state": {"judge_decision": "Research Manager Final Judgment: Hold"},
        "risk_debate_state": {"judge_decision": "Risk manager s final judgment: Sell"},
    }
    progress_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    records = _build_progress_records(progress_path, payload)

    assert len(records) == 2
    assert {record.target_agent_id for record in records} == {"research_manager_v2", "risk_manager_v2"}
    assert all(record.ticker == "000002" for record in records)
    assert all(record.analysis_date == "2025-08-01" for record in records)
    assert all(record.source_kind == REPORT_SOURCE_PROGRESS_JSON for record in records)


def test_build_store_metadata_adds_mem0_filters_and_source_details(tmp_path):
    report_path = (
        tmp_path
        / "data"
        / "analysis_results"
        / "000002"
        / "2025-08-20"
        / "reports"
        / "risk_management_decision.md"
    )
    report_path.parent.mkdir(parents=True)
    report_path.write_text("{'judge_decision': 'Risk Management Committee Chairman Recommends Sell'}", encoding="utf-8")

    record = _build_analysis_result_record(report_path)
    metadata = _build_store_metadata(record)

    assert metadata["source"] == MIGRATION_SOURCE
    assert metadata["target_agent_id"] == "risk_manager_v2"
    assert metadata["source_kind"] == REPORT_SOURCE_ANALYSIS_RESULTS
    assert metadata["source_file"] == "data/analysis_results/000002/2025-08-20/reports/risk_management_decision.md"
    assert metadata["ticker"] == "000002"
    assert metadata["symbol"] == "000002"
    assert metadata["object_type"] == "stock"
    assert metadata["object_key"] == "000002"
    assert metadata["analysis_date"] == "2025-08-20"

# === Merged from test_qmt_adapter_bootstrap.py ===
from app.services.data_sources.qmt_adapter import QMTAdapter


class _DummyXt:
    def __init__(self, connected: bool = False):
        self.connected = connected
        self.connect_calls = []

    def get_full_tick(self, _symbols):
        if not self.connected:
            raise RuntimeError("not connected")
        return {}

    def connect(self, port):
        self.connect_calls.append(port)


class _DummyXtDataCenter:
    def __init__(self):
        self.init_calls = []
        self.listen_calls = []
        self.data_dirs = []

    def set_data_home_dir(self, value):
        self.data_dirs.append(value)

    def set_token(self, _value):
        raise AssertionError("set_token should not be called in these tests")

    def set_allow_optmize_address(self, _value):
        raise AssertionError("set_allow_optmize_address should not be called in these tests")

    def set_kline_mirror_markets(self, _value):
        raise AssertionError("set_kline_mirror_markets should not be called in these tests")

    def set_kline_mirror_enabled(self, _value):
        raise AssertionError("set_kline_mirror_enabled should not be called in these tests")

    def set_init_markets(self, _value):
        pass

    def init(self, start_local_service=False):
        self.init_calls.append(start_local_service)

    def listen(self, port):
        self.listen_calls.append(port)
        return 58620


def _set_default_qmt_env(monkeypatch) -> None:
    monkeypatch.setenv("QMT_DATA_DIR", r"D:\gjzq\bin.x64")
    monkeypatch.setenv("QMT_LISTEN_PORT", "0")
    monkeypatch.setenv("QMT_LISTEN_PORT_RANGE", "58620-58650")
    monkeypatch.setenv("QMT_INIT_MARKETS", "SH,SZ")
    monkeypatch.setenv("QMT_TOKEN", "")
    monkeypatch.setenv("QMT_ALLOW_OPTIMIZE_ADDRESSES", "")
    monkeypatch.setenv("QMT_KLINE_MIRROR_MARKETS", "")
    monkeypatch.setenv("QMT_KLINE_MIRROR_ENABLED", "false")
    monkeypatch.setenv("QMT_START_LOCAL_SERVICE", "false")


def test_bootstrap_skips_active_init_for_default_miniqmt_mode(monkeypatch):
    _set_default_qmt_env(monkeypatch)

    dummy_xt = _DummyXt(connected=False)
    dummy_xtdc = _DummyXtDataCenter()

    monkeypatch.setattr("app.services.data_sources.qmt_adapter._get_xtdata", lambda: dummy_xt)
    monkeypatch.setattr("app.services.data_sources.qmt_adapter._get_xtdatacenter", lambda: dummy_xtdc)

    adapter = QMTAdapter()
    adapter._bootstrap_connection()

    assert dummy_xtdc.init_calls == []
    assert dummy_xtdc.listen_calls == []
    assert dummy_xt.connect_calls == []


def test_bootstrap_initializes_when_local_service_is_explicitly_enabled(monkeypatch):
    _set_default_qmt_env(monkeypatch)
    monkeypatch.setenv("QMT_START_LOCAL_SERVICE", "true")

    dummy_xt = _DummyXt(connected=False)
    dummy_xtdc = _DummyXtDataCenter()

    monkeypatch.setattr("app.services.data_sources.qmt_adapter._get_xtdata", lambda: dummy_xt)
    monkeypatch.setattr("app.services.data_sources.qmt_adapter._get_xtdatacenter", lambda: dummy_xtdc)

    adapter = QMTAdapter()
    adapter._bootstrap_connection()

    assert dummy_xtdc.data_dirs == [r"D:\gjzq\bin.x64"]
    assert dummy_xtdc.init_calls == [True]
    assert dummy_xtdc.listen_calls == [(58620, 58650)]
    assert dummy_xt.connect_calls == [58620]

# === Merged from test_report_exporter_markdown.py ===
from app.utils.report_exporter import ReportExporter


def test_generate_markdown_report_hides_internal_module_keys_and_role_ids():
	exporter = ReportExporter()
	report_doc = {
		"stock_symbol": "000001",
		"analysis_date": "2026-04-11 00:00:00",
		"analysts": [
			"market_analyst",
			"bull_researcher",
			"risky_analyst",
		],
		"research_depth": "fast",
		"summary": "Here is the summary.",
		"reports": {
			"market_report": "## core observation\n\n Here is the market technology research content.",
			"trader_investment_plan": "## Research summary\n\n Here is the user version of the research briefing.",
			"final_trade_decision": "## Comprehensive research conclusion\n\n Here is the comprehensive research conclusion.\n\n**Disclaimer**: Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary.",
			"bull_researcher": "## core proposition\n\n Here is the optimistic scenario argument.",
			"risky_analyst": "## Scenario conclusion\n\n Here s what the high-resilience scenario assessment looks like.",
		},
	}

	markdown_content = exporter.generate_markdown_report(report_doc)

	assert "bull_researcher" not in markdown_content
	assert "trader_investment_plan" not in markdown_content
	assert "final_trade_decision" not in markdown_content
	assert "risky_analyst" not in markdown_content
	assert "**analyst**: Market Technical Analyst, optimistic scenario argument, Highly resilient scenario assessment" in markdown_content
	assert "## 🧩 User version research briefing" in markdown_content
	assert "## 📝 Comprehensive research conclusion" in markdown_content
	assert "## 🌤️ optimistic scenario argument" in markdown_content
	assert "## ⚡ Highly resilient scenario assessment" in markdown_content
	assert markdown_content.index("## 🧩 User version research briefing") < markdown_content.index("## 📝 Comprehensive research conclusion")
	assert markdown_content.index("## 🧩 User version research briefing") < markdown_content.index("## 📈 Market Technology Research Report")
	assert "## Comprehensive research conclusion" not in markdown_content
	assert "### core observation" in markdown_content
	assert "Investment is risky and decisions need to be made with caution" not in markdown_content
	assert "This report is for research reference only and does not constitute individual stock recommendation, investment advice or operation basis. Please make independent judgments based on public information disclosure and your own research." in markdown_content


def test_generate_markdown_report_normalizes_chinese_numbered_subsections():
	exporter = ReportExporter()
	report_doc = {
		"stock_symbol": "000001",
		"analysis_date": "2026-04-11 00:00:00",
		"research_depth": "fast",
		"reports": {
			"index_report": "## 1. Core Observations\n\n Volume can rebound but structural differentiation remains.\n\n 2. Follow-up attention\n\n Pay attention to policy catalysis and transaction sustainability.",
			"sector_report": "**1. Prosperity clues**\n\n The plate rotation speed is accelerated.\n\n**2. Key points of verification**\n\n Observe whether the main line transactions continue.",
		},
	}

	markdown_content = exporter.generate_markdown_report(report_doc)

	assert "## 📊 Market Environment Research Report" in markdown_content
	assert "## 🏭 Industry sector research report" in markdown_content
	assert "### core observation" in markdown_content
	assert "### Follow up" in markdown_content
	assert "### Business clues" in markdown_content
	assert "### Verification points" in markdown_content
	assert "### 1. Core Observations" not in markdown_content
	assert "### 2. Follow-up attention" not in markdown_content
	assert "1. Prosperity clues" not in markdown_content
	assert "2. Key points of verification" not in markdown_content

# === Merged from test_report_formatter_reports_field.py ===
from app.utils.report_formatter import extract_reports_from_state, generate_summary_recommendation


def test_extract_reports_from_state_prefers_nested_reports_mapping():
    state = {
        "analysis_id": "demo-analysis",
        "reports": {
            "fundamentals_report": "# fundamental analysis\n\n The company s profitability has improved and its cash flow performance has been stable.",
            "neutral_analyst": "# Ping An Bank (000001) Scenario Balancing and Weight of Evidence Review Report\n\n## 1. Core Situation Judgment\n\n The current situation is closer to the baseline scenario.",
            "risk_management_decision": {
                "content": "# Risk Governance Summary\n\n## core risk\n\n It is necessary to continue to track changes in asset quality."
            },
        },
    }

    reports = extract_reports_from_state(state)

    assert "fundamentals_report" in reports
    assert "neutral_analyst" in reports
    assert "risk_management_decision" in reports
    assert "Improved profitability" in reports["fundamentals_report"]
    assert "core situational judgment" in reports["neutral_analyst"]
    assert "core risk" in reports["risk_management_decision"]


def test_generate_summary_recommendation_prefers_trader_brief_over_final_decision():
    reports = {
        "final_trade_decision": "# Comprehensive research conclusion\n\n This is an internal synthesis conclusion and should be used as a secondary fallback." * 4,
        "trader_investment_plan": "# User version research briefing\n\n One-sentence conclusion: The current situation is closer to neutral and more cautious. The follow-up focus will be on whether asset quality and transaction recovery continue.\n\n Why we think so: The valuation is not high, but the catalytic and verification data are not solid enough.",
    }

    summary, recommendation = generate_summary_recommendation(
        reports,
        {"action": "Neutral", "reasoning": "Waiting for more verification data."},
        "000001",
    )

    assert "One sentence conclusion" in summary
    assert "internal comprehensive conclusion" not in summary
    assert "Research opinion: Neutral" in recommendation

# === Merged from test_sse_heartbeat.py ===
# -*- coding: utf-8 -*-
"""SSE Heartbeat wrapper testing.

Regression (real bug): old implementation `wait_for(gen.__anext__(), timeout=15)` timeout in heartbeat
CancelledError will be injected into the underlying generator, the first time >15s Silent (long tool execution, e.g.
Valuation Excel generates 30-180s) kills the entire stream.
"""

import asyncio

import pytest

from app.routers.intelligent_assistant import sse_stream_with_heartbeat


async def _collect(agen, max_items=100):
    items = []
    async for chunk in agen:
        items.append(chunk)
        if len(items) >= max_items:
            break
    return items


class TestSseHeartbeat:
    @pytest.mark.asyncio
    async def test_long_silence_survives_and_delivers_keepalives(self):
        """The underlying generator survives after being silent for more than a few heartbeat cycles, and normal output arrives after the heartbeat."""

        async def slow_gen():
            await asyncio.sleep(0.25)  # Approximately 5 heartbeat cycles (interval=0.05) 
            yield "event: data\ndata: final\n\n"

        items = await _collect(sse_stream_with_heartbeat(slow_gen(), heartbeat_interval=0.05))

        assert "event: data\ndata: final\n\n" in items
        keepalives = [i for i in items if i == ": keepalive\n\n"]
        assert len(keepalives) >= 3, f"The heartbeat should continue to be sent during the long silent period. In fact, {len(keepalives)} Article"

    @pytest.mark.asyncio
    async def test_normal_chunks_pass_through(self):
        async def gen():
            for i in range(3):
                yield f"chunk-{i}"

        items = await _collect(sse_stream_with_heartbeat(gen(), heartbeat_interval=5))
        assert items == ["chunk-0", "chunk-1", "chunk-2"]

    @pytest.mark.asyncio
    async def test_generator_exception_becomes_error_event(self):
        async def boom():
            yield "before"
            raise RuntimeError("The tool exploded")
            yield "after"  # noqa: unreachable

        items = await _collect(sse_stream_with_heartbeat(boom(), heartbeat_interval=5))
        assert items[0] == "before"
        assert any(i.startswith("event: error") and "The tool exploded" in i for i in items[1:])

    @pytest.mark.asyncio
    async def test_early_client_close_cancels_generator(self):
        """When the consumer is shut down prematurely (simulating a client disconnect), the underlying generator is canceled and cleanup is completed."""
        cancelled = asyncio.Event()

        async def gen():
            try:
                await asyncio.sleep(10)
                yield "never"
            except asyncio.CancelledError:
                cancelled.set()
                raise

        # Short heartbeat: The first time __anext__ gets the heartbeat, the underlying generator is still hanging on sleep
        wrapped = sse_stream_with_heartbeat(gen(), heartbeat_interval=0.05)
        first = await wrapped.__anext__()
        assert first == ": keepalive\n\n"
        await wrapped.aclose()
        # Leave a cycle for cancellation propagation
        await asyncio.sleep(0.05)
        assert cancelled.is_set()

    @pytest.mark.asyncio
    async def test_old_antipattern_demonstration(self):
        """Controlled Experiment: Old Model (wait_for(__anext__)) Will indeed kill the generator.
        This test hardens the defective behavior and prevents someone from changing the wrapper back to the old mode."""

        async def slow_gen():
            await asyncio.sleep(30)
            yield "late"

        g = slow_gen()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(g.__anext__(), timeout=0.05)
        # Old mode: The generator has been unkilled
        with pytest.raises(StopAsyncIteration):
            await g.__anext__()

# === Merged from test_trace_id.py ===
import re
import logging
import io
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.request_id import RequestIDMiddleware
from app.core.logging_config import setup_logging
from app.core.logging_context import LoggingContextFilter


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def create_app():
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/t")
    async def t():
        logging.getLogger("webapi").info("trace test log")
        return {"ok": True}

    return app


def test_trace_id_header_and_logging():
    # Arrange
    setup_logging("INFO")
    app = create_app()
    client = TestClient(app)

    # Attach a temporary stream handler to capture only webapi logs with trace_id
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.INFO)
    handler.addFilter(LoggingContextFilter())
    handler.setFormatter(logging.Formatter("%(trace_id)s|%(message)s"))

    logger = logging.getLogger("webapi")
    logger.addHandler(handler)

    try:
        # Act
        resp = client.get("/t")

        # Assert headers
        trace_id = resp.headers.get("X-Trace-ID")
        assert trace_id and UUID_RE.match(trace_id)
        assert resp.headers.get("X-Request-ID") == trace_id

        # Assert our captured log contains trace_id
        output = stream.getvalue()
        assert f"{trace_id}|trace test log" in output
    finally:
        logger.removeHandler(handler)
        handler.close()

