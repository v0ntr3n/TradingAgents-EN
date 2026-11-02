from __future__ import annotations

# === Merged from test_akshare_historical_error_handling.py ===
import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd

from app.routers.stock_sync import _build_single_historical_sync_result
from tradingagents.dataflows.providers.china.akshare import AKShareNetworkError, AKShareProvider


def test_get_historical_data_falls_back_to_tx_after_primary_network_error():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider.ak = Mock()
    provider.ak.stock_zh_a_hist = Mock(side_effect=ConnectionAbortedError("Connection aborted."))
    provider.ak.stock_zh_a_hist_tx = Mock(return_value=pd.DataFrame([
        {"date": "2026-04-28", "open": 426.19, "high": 433.3, "low": 423.0, "close": 427.67, "amount": 14992134063.0},
        {"date": "2026-04-29", "open": 430.0, "high": 435.0, "low": 428.0, "close": 432.0, "amount": 8600000000.0},
    ]))

    with patch('tradingagents.dataflows.providers.china.akshare.asyncio.sleep', new=AsyncMock()):
        result = asyncio.run(provider.get_historical_data("300750", "2026-04-01", "2026-04-29"))

    assert result is not None
    assert len(result) == 2
    assert list(result["code"].unique()) == ["300750"]
    assert result.iloc[-1]["close"] == 432.0
    provider.ak.stock_zh_a_hist_tx.assert_called_once_with(
        symbol="sz300750",
        start_date="2026-04-01",
        end_date="2026-04-29",
        adjust="qfq",
    )


def test_get_historical_data_falls_back_to_sina_daily_after_tx_failure():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider.ak = Mock()
    provider.ak.stock_zh_a_hist = Mock(side_effect=ConnectionAbortedError("Connection aborted."))
    provider.ak.stock_zh_a_hist_tx = Mock(side_effect=ValueError("invalid literal for int() with base 10: 'i'"))
    provider.ak.stock_zh_a_daily = Mock(return_value=pd.DataFrame([
        {"date": "2026-04-28", "open": 426.19, "high": 433.3, "low": 423.0, "close": 427.67, "volume": 35012113.0, "amount": 14992134063.0, "turnover": 0.0082},
        {"date": "2026-04-29", "open": 430.0, "high": 435.0, "low": 428.0, "close": 432.0, "volume": 20000000.0, "amount": 8600000000.0, "turnover": 0.0047},
    ]))

    with patch('tradingagents.dataflows.providers.china.akshare.asyncio.sleep', new=AsyncMock()):
        result = asyncio.run(provider.get_historical_data("300750", "2026-04-01", "2026-04-29"))

    assert result is not None
    assert len(result) == 2
    assert list(result["code"].unique()) == ["300750"]
    assert result.iloc[-1]["close"] == 432.0


def test_get_historical_data_raises_network_error_when_primary_and_fallback_both_fail():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider.ak = Mock()
    provider.ak.stock_zh_a_hist = Mock(side_effect=ConnectionAbortedError("Connection aborted."))
    provider.ak.stock_zh_a_hist_tx = Mock(side_effect=ConnectionAbortedError("Connection aborted."))
    provider.ak.stock_zh_a_daily = Mock(side_effect=ConnectionAbortedError("Connection aborted."))

    with patch('tradingagents.dataflows.providers.china.akshare.asyncio.sleep', new=AsyncMock()):
        try:
            asyncio.run(provider.get_historical_data("300750", "2026-04-01", "2026-04-29"))
            assert False, "expected AKShareNetworkError"
        except AKShareNetworkError as exc:
            assert "300750 Network connection interrupted" in str(exc)


def test_build_single_historical_sync_result_prefers_real_error_message():
    result = _build_single_historical_sync_result({
        "success_count": 0,
        "error_count": 1,
        "total_records": 0,
        "errors": [{"error": "300750 The network connection is interrupted. It is recommended to try again later or reduce the time range."}],
    })

    assert result == {
        "success": False,
        "records": 0,
        "error": "300750 The network connection is interrupted. It is recommended to try again later or reduce the time range."
    }

# === Merged from test_akshare_manual_mode.py ===
import asyncio
from unittest.mock import AsyncMock, Mock

from app.worker.akshare_sync_service import AKShareSyncService


def test_sync_historical_data_manual_mode_ignores_scheduler_cancel_state():
    service = AKShareSyncService()
    service.db = Mock()
    service.provider = Mock()
    service._current_job_id = "akshare_historical_sync"
    service._should_stop = AsyncMock(return_value=True)
    service._process_historical_batch = AsyncMock(return_value={
        "success_count": 1,
        "error_count": 0,
        "total_records": 5,
        "errors": [],
        "processed_count": 1,
    })

    result = asyncio.run(service.sync_historical_data(
        symbols=["300750"],
        start_date="2026-04-01",
        end_date="2026-04-29",
        incremental=False,
        manual_mode=True,
    ))

    assert result["success_count"] == 1
    assert result["total_records"] == 5
    assert result.get("stopped") is not True
    service._should_stop.assert_not_awaited()
    service._process_historical_batch.assert_awaited_once()

# === Merged from test_akshare_provider_basic_info.py ===
import asyncio
from unittest.mock import AsyncMock, patch

from tradingagents.dataflows.providers.china.akshare import AKShareProvider


def test_get_stock_basic_info_for_single_sync_uses_stable_sources_before_detail_fallback():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider._get_single_stock_profile_info = AsyncMock(return_value={
        "name": "Ping An Bank",
        "industry": "money financial services",
        "list_date": "1991-04-03",
        "market": "motherboard",
        "sse": "Shenzhen Stock Exchange",
    })
    provider._get_single_stock_listing_info = AsyncMock(return_value={
        "market": "motherboard",
    })
    provider._get_single_stock_spot_info = AsyncMock(return_value={
        "total_mv": 2235.56,
        "circ_mv": 2235.52,
        "pe_ttm": 5.19,
        "pb": 0.48,
    })
    provider._get_stock_info_detail = AsyncMock(return_value={
        "code": "000001",
        "_detail_fetch_failed": True,
        "_detail_fetch_error": "should not be used",
        "_detail_symbol": "sz000001",
    })

    result = asyncio.run(provider.get_stock_basic_info_for_single_sync("000001"))

    assert result is not None
    assert result["sync_status"] == "success"
    assert result["name"] == "Ping An Bank"
    assert result["industry"] == "money financial services"
    assert result["list_date"] == "1991-04-03"
    assert result["total_mv"] == 2235.56
    assert result["pb"] == 0.48
    provider._get_stock_info_detail.assert_not_awaited()


def test_get_stock_basic_info_for_single_sync_returns_degraded_when_all_sources_fail():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider._get_single_stock_profile_info = AsyncMock(return_value={})
    provider._get_single_stock_listing_info = AsyncMock(return_value={})
    provider._get_single_stock_spot_info = AsyncMock(return_value={})
    provider._get_stock_info_detail = AsyncMock(return_value={
        "code": "000001",
        "_detail_fetch_failed": True,
        "_detail_fetch_error": "AKShare Network abnormality in individual stock details interface",
        "_detail_symbol": "sz000001",
    })

    result = asyncio.run(provider.get_stock_basic_info_for_single_sync("000001"))

    assert result is not None
    assert result["sync_status"] == "degraded"
    assert result["detail_fetch_error"] == "AKShare Network abnormality in individual stock details interface"
    assert result["detail_fetch_symbol"] == "sz000001"
    provider._get_stock_info_detail.assert_awaited_once()

# === Merged from test_akshare_provider_quotes.py ===
import asyncio
from unittest.mock import Mock, patch

import pandas as pd

from tradingagents.dataflows.providers.china.akshare import AKShareProvider


def test_get_stock_quotes_handles_dash_placeholder_values():
    with patch.object(AKShareProvider, "_initialize_akshare", return_value=None):
        provider = AKShareProvider()

    provider.connected = True
    provider.ak = Mock()
    provider.ak.stock_bid_ask_em = Mock(return_value=pd.DataFrame([
        {"item": "Latest", "value": 432.93},
        {"item": "Increase", "value": 1.23},
        {"item": "ups and downs", "value": 5.26},
        {"item": "Chief", "value": "-"},
        {"item": "Amount", "value": "-"},
        {"item": "Change hands", "value": 0.0},
        {"item": "Quantity ratio", "value": "-"},
        {"item": "highest", "value": "-"},
        {"item": "lowest", "value": "-"},
        {"item": "Open today", "value": "-"},
        {"item": "Collected yesterday", "value": 427.67},
    ]))

    quotes = asyncio.run(provider.get_stock_quotes("300750"))

    assert quotes is not None
    assert quotes["code"] == "300750"
    assert quotes["price"] == 432.93
    assert quotes["change_percent"] == 1.23
    assert quotes["volume"] == 0
    assert quotes["amount"] == 0.0
    assert quotes["open"] == 0.0
    assert quotes["high"] == 0.0
    assert quotes["low"] == 0.0
    assert quotes["volume_ratio"] == 0.0
    assert quotes["pre_close"] == 427.67

# === Merged from test_akshare_sync_service.py ===
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.worker.akshare_sync_service import AKShareSyncService


class AsyncCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        self._iterator = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


@pytest.fixture
def akshare_sync_service():
    service = AKShareSyncService()
    service.db = Mock()
    service.provider = Mock()
    service._is_data_fresh = Mock(return_value=True)
    return service


@pytest.mark.asyncio
async def test_process_basic_info_batch_updates_fresh_record_when_mapping_can_fill_industry(akshare_sync_service):
    akshare_sync_service.db.stock_basic_info.find_one = AsyncMock(return_value={
        "code": "000001",
        "source": "akshare",
        "industry": "unknown",
        "updated_at": datetime.utcnow(),
    })
    akshare_sync_service.db.stock_basic_info.update_one = AsyncMock(return_value=Mock(modified_count=1, upserted_id=None))

    with patch('app.services.official_industry_service.fetch_industry_mapping', new_callable=AsyncMock, return_value={"000001": "bank"}):
        result = await akshare_sync_service._process_basic_info_batch([
            {"code": "000001", "name": "Ping An Bank"}
        ], force_update=False)

    assert result["success_count"] == 1
    assert result["skipped_count"] == 0
    update_filter = akshare_sync_service.db.stock_basic_info.update_one.await_args.args[0]
    update_payload = akshare_sync_service.db.stock_basic_info.update_one.await_args.args[1]["$set"]
    assert update_filter == {"code": "000001", "source": "akshare"}
    assert update_payload["industry"] == "bank"
    assert update_payload["industry_source"] == "system_industry_mapping"


@pytest.mark.asyncio
async def test_process_basic_info_batch_skips_fresh_record_when_mapping_already_matches(akshare_sync_service):
    akshare_sync_service.db.stock_basic_info.find_one = AsyncMock(return_value={
        "code": "000001",
        "source": "akshare",
        "industry": "bank",
        "updated_at": datetime.utcnow(),
    })
    akshare_sync_service.db.stock_basic_info.update_one = AsyncMock(return_value=Mock(modified_count=0, upserted_id=None))

    with patch('app.services.official_industry_service.fetch_industry_mapping', new_callable=AsyncMock, return_value={"000001": "bank"}):
        result = await akshare_sync_service._process_basic_info_batch([
            {"code": "000001", "name": "Ping An Bank"}
        ], force_update=False)

    assert result["success_count"] == 0
    assert result["skipped_count"] == 1
    akshare_sync_service.db.stock_basic_info.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_favorite_stocks_uses_valid_user_favorites_only(akshare_sync_service):
    akshare_sync_service.db.users.find = Mock(return_value=AsyncCursor([
        {"_id": "user-1"},
        {"_id": "user-2"},
    ]))
    akshare_sync_service.db.user_favorites.find = Mock(return_value=AsyncCursor([
        {
            "user_id": "user-1",
            "favorites": [
                {"stock_code": "000001"},
                {"stock_code": "000002"},
            ],
        },
        {
            "user_id": "user-2",
            "favorites": [
                {"stock_code": "000002"},
                {"stock_code": "000003"},
            ],
        },
        {
            "user_id": "stale-user",
            "favorites": [
                {"stock_code": "999999"},
            ],
        },
    ]))

    result = await akshare_sync_service._get_favorite_stocks()

    assert result == ["000001", "000002", "000003"]
    akshare_sync_service.db.users.find.assert_called_once_with({}, {"_id": 1})
    akshare_sync_service.db.user_favorites.find.assert_called_once_with(
        {"favorites": {"$exists": True, "$ne": []}},
        {"user_id": 1, "favorites.stock_code": 1, "_id": 0},
    )

# === Merged from test_data_source_manager_availability.py ===
from app.services.data_sources.manager import DataSourceManager


class _DummyAdapter:
    def __init__(self, name: str, available: bool):
        self._name = name
        self._available = available
        self._priority = 1
        self.probe_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority

    def is_available(self) -> bool:
        self.probe_count += 1
        return self._available


def test_disabled_data_source_is_skipped_before_probe() -> None:
    manager = DataSourceManager.__new__(DataSourceManager)
    qmt = _DummyAdapter("qmt", available=False)
    akshare = _DummyAdapter("akshare", available=True)

    manager.adapters = [qmt, akshare]
    manager._configured_enabled_map = {"qmt": False, "akshare": True}

    available = manager.get_available_adapters()

    assert qmt.probe_count == 0
    assert akshare.probe_count == 1
    assert available == [akshare]

# === Merged from test_data_source_priority.py ===
from app.core.data_source_priority import _merge_grouped_enabled_sources
from app.models.config import DataSourceConfig, DataSourceType


def _build_config(name: str, source_type: DataSourceType, priority: int, enabled: bool = True) -> DataSourceConfig:
    return DataSourceConfig(
        name=name,
        type=source_type,
        enabled=enabled,
        priority=priority,
    )


def test_category_disable_excludes_source_from_current_market():
    configs = [
        _build_config("Tushare", DataSourceType.TUSHARE, 30),
        _build_config("AKShare", DataSourceType.AKSHARE, 20),
        _build_config("BaoStock", DataSourceType.BAOSTOCK, 10),
    ]
    groupings = [
        {"data_source_name": "baostock", "enabled": False, "priority": 100},
        {"data_source_name": "tushare", "enabled": True, "priority": 90},
    ]

    assert _merge_grouped_enabled_sources(configs, groupings) == ["tushare", "akshare"]


def test_global_disable_overrides_grouping_enable():
    configs = [
        _build_config("Tushare", DataSourceType.TUSHARE, 30),
        _build_config("BaoStock", DataSourceType.BAOSTOCK, 10, enabled=False),
    ]
    groupings = [
        {"data_source_name": "baostock", "enabled": True, "priority": 100},
        {"data_source_name": "tushare", "enabled": True, "priority": 90},
    ]

    assert _merge_grouped_enabled_sources(configs, groupings) == ["tushare"]


def test_ungrouped_enabled_sources_fall_back_to_global_priority():
    configs = [
        _build_config("Tushare", DataSourceType.TUSHARE, 30),
        _build_config("AKShare", DataSourceType.AKSHARE, 20),
        _build_config("Local", DataSourceType.LOCAL, 40),
    ]
    groupings = [
        {"data_source_name": "local", "enabled": True, "priority": 100},
    ]

    assert _merge_grouped_enabled_sources(configs, groupings) == ["local", "tushare", "akshare"]

# === Merged from test_fundamentals_analyst_v2_adapter.py ===
from langchain_core.messages import HumanMessage


def test_build_user_prompt_keeps_state_company_name_when_market_lookup_empty(monkeypatch):
    from core.agents.adapters import fundamentals_analyst_v2 as module

    agent = module.FundamentalsAnalystAgentV2()
    captured = {}

    class FakeStockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {
                "market_name": "China A shares",
                "currency_name": "RMB",
                "currency_symbol": "¥",
                "company_name": "",
            }

    def fake_get_prompt_from_template(*args, **kwargs):
        captured["variables"] = kwargs["variables"]
        return "PROMPT"

    monkeypatch.setattr(module, "StockUtils", FakeStockUtils)
    agent._get_prompt_from_template = fake_get_prompt_from_template

    prompt = agent._build_user_prompt(
        ticker="000001",
        trade_date="2026-04-10",
        state={"company_name": "Ping An Bank"},
    )

    assert prompt == "PROMPT"
    assert captured["variables"]["company_name"] == "Ping An Bank"


def test_execute_prefetches_required_china_tools_and_uses_analysis_prompt(monkeypatch):
    from core.agents.adapters import fundamentals_analyst_v2 as module

    agent = module.FundamentalsAnalystAgentV2()
    agent._llm = object()

    prefetched_calls = []

    class FakeTool:
        def __init__(self, name, result):
            self.name = name
            self._result = result

        def invoke(self, tool_args):
            prefetched_calls.append((self.name, tool_args))
            return self._result

    class FakeStockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {"is_china": True, "market_name": "China A shares"}

    monkeypatch.setattr(module, "StockUtils", FakeStockUtils)

    agent._langchain_tools = [
        FakeTool("get_stock_fundamentals_unified", "UNIFIED"),
        FakeTool("get_financial_statements", "FINANCIALS"),
        FakeTool("get_cash_flow_statement", "CASHFLOW"),
        FakeTool("get_peer_comparison", "PEERS"),
    ]

    agent._build_system_prompt = lambda state: "SYSTEM"
    agent._build_user_prompt = lambda ticker, trade_date, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["messages"] = messages
        captured["analysis_prompt"] = analysis_prompt
        captured["tools_during_call"] = [tool.name for tool in agent._langchain_tools]
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute({
        "ticker": "000001",
        "trade_date": "2026-04-10",
        "company_name": "Ping An Bank",
    })

    assert result["fundamentals_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["tools_during_call"] == ["get_peer_comparison"]
    assert [name for name, _ in prefetched_calls] == [
        "get_stock_fundamentals_unified",
        "get_financial_statements",
        "get_cash_flow_statement",
    ]

    prefetch_messages = [msg for msg in captured["messages"] if isinstance(msg, HumanMessage) and "prefetched" in msg.content]
    assert len(prefetch_messages) == 1
    assert "UNIFIED" in prefetch_messages[0].content
    assert "FINANCIALS" in prefetch_messages[0].content
    assert "CASHFLOW" in prefetch_messages[0].content

# === Merged from test_fundamentals_prompt_compliance.py ===
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fundamentals_analyst_v2_templates_are_research_mode() -> None:
    templates_path = ROOT / "exports" / "current_db_templates.json"
    templates = json.loads(templates_path.read_text(encoding="utf-8"))

    target_templates = [
        item for item in templates
        if item.get("agent_name") == "fundamentals_analyst_v2"
        and item.get("template_name") in {
            "Fundamental Analyst v2.0 - Aggressive",
            "Fundamental Analyst v2.0 - Neutral",
            "Fundamental Analyst v2.0 - Conservative",
        }
    ]

    assert len(target_templates) == 3

    required_phrases = [
        "core observation",
        "Financial and operating signals",
        "Valuation background",
        "valuation premium",
        "Summary",
        "get_financial_statements",
        "get_cash_flow_statement",
        "get_peer_comparison",
        "Tool results not provided",
        "Cumulative caliber during the reporting period",
        "Single quarter derivation",
        "Industry characteristics",
        "Not applicable",
        "Historical financials, historical valuation ranges and disclosed operating data",
        "Current stock price, rise and fall, trading volume, current total market capitalization",
        "snapshot date",
        "must not be written as As of analysis date Or replace the valuation date with the analysis date",
        "You can t just change the date without explaining the reason",
        "core observation` Article 1 or `## Valuation background` Beginning",
        "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day.",
        "Do not end the report directly",
    ]

    for template in target_templates:
        content = template["content"]
        combined_text = "\n".join(str(content.get(field, "")) for field in content)
        output_format = str(content.get("output_format", ""))
        user_prompt = str(content.get("user_prompt", ""))
        analysis_requirements = str(content.get("analysis_requirements", ""))

        assert "price analysis range" not in output_format
        assert "Reasonable price range" not in output_format
        assert "Room for upside" not in output_format
        assert "Downside" not in output_format
        assert "Position recommendations" not in output_format
        assert "Risk exposure recommendations" not in output_format
        assert "Suggestions" not in output_format

        assert "No trading advice may be output" in user_prompt
        assert "target price" in user_prompt
        assert "Do not use LLM s own knowledge to supplement data" in user_prompt
        assert "The current stock price and current total market capitalization are not allowed to be included in the company profile, core observations or summary." in user_prompt
        assert "You must also indicate the snapshot date corresponding to the indicator." in user_prompt
        assert "must not be written as As of analysis date Or replace the valuation date with the analysis date" in user_prompt
        assert "You can t just change the date without explaining the reason" in user_prompt
        assert "core observation` Article 1 or `## Valuation background` Beginning" in user_prompt
        assert "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day." in user_prompt
        assert "You can write:" in user_prompt
        assert "Do not write:" in user_prompt
        assert "No need to list separately Questions to be verified " in user_prompt
        assert "Does not require mechanical coverage of all common financial indicators" in user_prompt
        assert "The results of get_stock_fundamentals_unified, get_financial_statements and get_cash_flow_statement must be obtained before generating the text." in user_prompt
        assert "Q2/Q3/Q4 Not a single quarter value" in combined_text
        assert (
            "Prioritize using these fields to analyze quarterly changes" in combined_text
            or "Prefer using this field to describe quarterly changes" in combined_text
        )
        assert "margin of safety" in user_prompt
        assert "Economic turning point" in user_prompt
        assert "No output allowed" in analysis_requirements
        assert "trading action" in analysis_requirements
        assert "Examples of expressions" in analysis_requirements
        assert "No need to list separately Questions to be verified " in analysis_requirements
        assert "Do not write its absence directly as a risk or data gap" in analysis_requirements
        assert "Must first obtain overall fundamentals, most recent quarter financial report details and most recent quarterly cash flow statement" in analysis_requirements
        assert "Also do not write these fields into `## Company Profile`, `## core observation`, `## Valuation background` or `## Summary`" in analysis_requirements
        assert "You must also indicate the snapshot date corresponding to the indicator." in analysis_requirements
        assert "must not be written as As of analysis date Or replace the valuation date with the analysis date" in analysis_requirements
        assert "You can t just change the date without explaining the reason" in analysis_requirements
        assert "core observation` Article 1 or `## Valuation background` Beginning" in analysis_requirements
        assert "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day." in analysis_requirements
        assert (
            "Do not add Q1-Q4 directly" in analysis_requirements
            or "Or add Q1-Q4 directly" in analysis_requirements
        )
        assert "Single quarter derivation" in combined_text
        assert "margin of safety" in analysis_requirements
        assert "Economic turning point" in analysis_requirements
        assert "Do not add any attribution information to the report" in combined_text
        assert "Prohibiting any false names, authorships or attributions" in combined_text

        for phrase in required_phrases:
            assert phrase in combined_text


def test_fundamentals_analyst_v2_default_tools_include_peer_comparison() -> None:
    adapter_source = (ROOT / "core" / "agents" / "adapters" / "fundamentals_analyst_v2.py").read_text(encoding="utf-8")
    config_source = (ROOT / "core" / "agents" / "config.py").read_text(encoding="utf-8")

    assert "default_tools=[\"get_stock_fundamentals_unified\", \"get_financial_statements\", \"get_cash_flow_statement\", \"get_peer_comparison\"]" in adapter_source
    assert "max_tool_calls=4" in adapter_source
    # config.py A more conservative default tool list is retained in the file, and the metadata in the adapter file shall prevail when running.
    assert "fundamentals_analyst_v2" in config_source

# === Merged from test_integrated_cache_manager.py ===
import logging
from datetime import datetime, timedelta

from tradingagents.dataflows.cache.integrated import IntegratedCacheManager


def _build_manager(use_adaptive: bool) -> IntegratedCacheManager:
    manager = IntegratedCacheManager.__new__(IntegratedCacheManager)
    manager.use_adaptive = use_adaptive
    manager.logger = logging.getLogger(__name__)
    return manager


def test_find_cached_stock_data_passes_max_age_to_legacy_cache():
    manager = _build_manager(use_adaptive=False)
    captured = {}

    class LegacyCache:
        def find_cached_stock_data(self, **kwargs):
            captured.update(kwargs)
            return "legacy-cache-key"

    manager.legacy_cache = LegacyCache()

    result = manager.find_cached_stock_data(
        symbol="000002.SZ",
        start_date="2026-04-01",
        end_date="2026-04-10",
        data_source="tushare",
        max_age_hours=24,
    )

    assert result == "legacy-cache-key"
    assert captured["symbol"] == "000002.SZ"
    assert captured["data_source"] == "tushare"
    assert captured["max_age_hours"] == 24


def test_find_cacched_stock_data_alias_is_backward_compatible():
    manager = _build_manager(use_adaptive=False)

    class LegacyCache:
        def find_cached_stock_data(self, **kwargs):
            return kwargs["symbol"]

    manager.legacy_cache = LegacyCache()

    result = manager.find_cacched_stock_data(symbol="000002.SZ", max_age_hours=12)

    assert result == "000002.SZ"


def test_find_cached_stock_data_honors_max_age_in_adaptive_mode():
    manager = _build_manager(use_adaptive=True)

    class AdaptiveCache:
        primary_backend = "file"
        fallback_enabled = False

        def find_cached_data(self, **kwargs):
            return "adaptive-cache-key"

        def _load_from_file(self, cache_key):
            assert cache_key == "adaptive-cache-key"
            return {"timestamp": datetime.now() - timedelta(hours=3)}

    manager.adaptive_cache = AdaptiveCache()

    expired = manager.find_cached_stock_data(symbol="000002.SZ", max_age_hours=1)
    fresh = manager.find_cached_stock_data(symbol="000002.SZ", max_age_hours=4)

    assert expired is None
    assert fresh == "adaptive-cache-key"

# === Merged from test_market_tool_dates.py ===
from datetime import datetime

import pandas as pd


def test_resolve_china_actual_data_date_rolls_back_before_open():
    from core.tools.implementations.market import stock_market_data as module

    effective_end_date, actual_data_date, note = module._resolve_china_actual_data_date(
        ticker="600519",
        requested_end_date="2026-04-13",
        now=datetime(2026, 4, 13, 9, 15),
        db_latest_trade_date="2026-04-10",
    )

    assert effective_end_date == "2026-04-10"
    assert actual_data_date == "2026-04-10"
    assert note is not None
    assert "Pre-market session" in note
    assert "2026-04-10" in note


def test_unified_market_tool_emits_actual_data_date_context(monkeypatch):
    from core.tools.implementations.market import stock_market_data as module
    from tradingagents.dataflows import interface as interface_module
    from tradingagents.utils import stock_utils as stock_utils_module

    class FakeStockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {
                "is_china": True,
                "is_hk": False,
                "is_us": False,
                "market_name": "China A shares",
                "currency_name": "RMB",
                "currency_symbol": "¥",
            }

    captured = {}

    def fake_get_china_stock_data_unified(ticker, start_date, end_date):
        captured["args"] = (ticker, start_date, end_date)
        return "MOCK_STOCK_DATA"

    monkeypatch.setattr(stock_utils_module, "StockUtils", FakeStockUtils)
    monkeypatch.setattr(interface_module, "get_china_stock_data_unified", fake_get_china_stock_data_unified)
    monkeypatch.setattr(module, "_ensure_fresh_china_data", lambda ticker: None)
    monkeypatch.setattr(
        module,
        "_resolve_china_actual_data_date",
        lambda ticker, requested_end_date, now=None, db_latest_trade_date=None: (
            "2026-04-10",
            "2026-04-10",
            "The requested analysis date is 2026-04-13, but it is currently in the pre-market period and daily data for the day has not yet been formed; the following prices and technical indicators are based on the most recently completed trading day, 2026-04-10.",
        ),
    )

    result = module.get_stock_market_data_unified.invoke(
        {
            "ticker": "600519",
            "start_date": "2026-04-13",
            "end_date": "2026-04-13",
        }
    )

    assert captured["args"] == ("600519", "2026-04-10", "2026-04-10")
    assert "**Request analysis date**: 2026-04-13" in result
    assert "**actual data date**: 2026-04-10" in result
    assert "Pre-market session" in result


def test_format_stock_data_response_includes_actual_data_date_note():
    from tradingagents.dataflows import data_source_manager as module

    manager = module.DataSourceManager.__new__(module.DataSourceManager)
    data = pd.DataFrame(
        {
            "date": pd.to_datetime(
                [
                    "2026-04-02",
                    "2026-04-06",
                    "2026-04-07",
                    "2026-04-08",
                    "2026-04-09",
                    "2026-04-10",
                ]
            ),
            "open": [1400.0, 1410.0, 1420.0, 1430.0, 1440.0, 1450.0],
            "high": [1410.0, 1420.0, 1430.0, 1440.0, 1450.0, 1460.0],
            "low": [1390.0, 1405.0, 1415.0, 1425.0, 1435.0, 1445.0],
            "close": [1405.0, 1415.0, 1425.0, 1435.0, 1445.0, 1455.0],
            "volume": [1000, 1100, 1200, 1300, 1400, 1500],
        }
    )

    result = manager._format_stock_data_response(
        data,
        symbol="600519",
        stock_name="Kweichow Moutai",
        start_date="2026-04-13",
        end_date="2026-04-13",
    )

    assert "Request analysis date: 2026-04-13" in result
    assert "actual data date: 2026-04-10" in result
    assert "date description: Requested analysis date 2026-04-13 No complete daily data yet" in result

# === Merged from test_news_social_analyst_v2_adapter.py ===
def test_news_execute_uses_default_analysis_prompt(monkeypatch):
    from core.agents.adapters import news_analyst_v2 as module

    agent = module.NewsAnalystV2()
    agent._llm = object()
    agent._langchain_tools = [type("FakeTool", (), {"name": "get_stock_news_unified"})()]

    monkeypatch.setattr(module, "StockUtils", None)

    agent._build_system_prompt = lambda market_type=None, context=None, state=None: "SYSTEM"
    agent._build_user_prompt = lambda ticker, analysis_date, tool_data, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["analysis_prompt"] = analysis_prompt
        captured["message_count"] = len(messages)
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute(
        {
            "ticker": "000001",
            "analysis_date": "2026-04-13",
            "company_name": "Ping An Bank",
        }
    )

    assert result["news_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["message_count"] == 2


def test_news_default_analysis_prompt_contains_legacy_structure_guards():
    from core.agents.adapters import news_analyst_v2 as module

    agent = module.NewsAnalystV2()
    prompt = agent._build_analysis_prompt("000001")

    assert "Latest news summary" in prompt
    assert "News impact analysis" in prompt
    assert "Market Sentiment Assessment" in prompt
    assert "analysis point of view" in prompt
    assert "Multiple headlines essentially describing the same event" in prompt
    assert "short term response expectations" in prompt
    assert "No need for separate chapters" in prompt
    assert "Do not output investment recommendations, target prices, price ranges, positions, or execution plans" in prompt


def test_social_execute_uses_default_analysis_prompt(monkeypatch):
    from core.agents.adapters import social_analyst_v2 as module

    agent = module.SocialMediaAnalystV2()
    agent._llm = object()
    agent._langchain_tools = [type("FakeTool", (), {"name": "get_stock_sentiment_unified"})()]

    monkeypatch.setattr(module, "StockUtils", None)

    agent._build_system_prompt = lambda market_type=None, context=None, state=None: "SYSTEM"
    agent._build_user_prompt = lambda ticker, analysis_date, tool_data, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["analysis_prompt"] = analysis_prompt
        captured["message_count"] = len(messages)
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute(
        {
            "ticker": "000001",
            "analysis_date": "2026-04-13",
            "company_name": "Ping An Bank",
        }
    )

    assert result["sentiment_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["message_count"] == 2


def test_social_default_analysis_prompt_contains_dimension_guards():
    from core.agents.adapters import social_analyst_v2 as module

    agent = module.SocialMediaAnalystV2()
    prompt = agent._build_analysis_prompt("000001")

    assert "If the tool explicitly states that the current results are from news fallback sentiment summaries" in prompt
    assert "Do not analyze this dimension" in prompt
    assert "Do not use The emotional turning point has arrived " in prompt
    assert "Do not output investment recommendations, target prices, price ranges, positions, or execution plans" in prompt

# === Merged from test_optimized_china_data_gross_margin.py ===
"""Unified fundamental tool gross profit margin analysis test."""

from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider


def test_parse_mongodb_financial_data_prefers_reasonable_grossprofit_margin() -> None:
    provider = OptimizedChinaDataProvider.__new__(OptimizedChinaDataProvider)
    financial_data = {
        "roe": 11.6,
        "roa": 0.84,
        "gross_margin": 139609610.88,
        "netprofit_margin": 12.9,
        "debt_to_assets": 45.2,
        "current_ratio": 1.6,
        "quick_ratio": 1.2,
        "cash_ratio": 0.8,
        "raw_data": {
            "financial_indicators": [
                {
                    "gross_margin": 139609610.88,
                    "grossprofit_margin": 26.8,
                }
            ]
        },
    }

    result = provider._parse_mongodb_financial_data(financial_data, 10.0)

    assert result.get("gross_margin") == "26.8%"

# === Merged from test_stock_data_result_normalization.py ===
from tradingagents.dataflows.data_source_manager import ChinaDataSource, DataSourceManager
from tradingagents.dataflows.optimized_china_data import _coerce_stock_info_text


def test_get_stock_data_normalizes_tuple_fallback_result(monkeypatch):
    manager = DataSourceManager.__new__(DataSourceManager)
    manager.current_source = ChinaDataSource.TUSHARE

    monkeypatch.setattr(
        manager,
        "_get_tushare_data",
        lambda symbol, start_date, end_date, period="daily": "❌ Current data source failed",
    )
    monkeypatch.setattr(
        manager,
        "_try_fallback_sources",
        lambda symbol, start_date, end_date, period="daily": ("Stock code: 000001\n Stock name: Ping An Bank", "mongodb"),
    )

    result = manager.get_stock_data("000001", "2026-04-08", "2026-04-10")

    assert isinstance(result, str)
    assert "Stock name: Ping An Bank" in result


def test_coerce_stock_info_text_accepts_tuple_payload():
    stock_info = (
        {
            "name": "Ping An Bank",
            "area": "Shenzhen",
            "industry": "bank",
            "market": "motherboard",
            "list_date": "19910403",
            "current_price": 12.34,
            "change_pct": 1.23,
            "volume": 456789,
        },
        "app_cache",
    )

    text = _coerce_stock_info_text(stock_info, "000001")

    assert "Stock code: 000001" in text
    assert "Stock name: Ping An Bank" in text
    assert "current price: 12.34" in text
    assert "Increase or decrease: +1.23%" in text

# === Merged from test_stock_sync_single_akshare_basic.py ===
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import BackgroundTasks

from app.routers.stock_sync import SingleStockSyncRequest, sync_single_stock


async def _fake_get_akshare_sync_service():
    provider = Mock()
    provider.get_stock_basic_info_for_single_sync = AsyncMock(return_value={
        "code": "300750",
        "name": "Ningde era",
        "industry": "Electrical machinery and equipment manufacturing",
        "market": "GEM",
        "sse": "Shenzhen Stock Exchange",
        "list_date": "2018-06-11",
        "sync_status": "success",
    })
    provider.get_stock_basic_info = AsyncMock(return_value=None)
    return SimpleNamespace(provider=provider)


def test_sync_single_stock_akshare_basic_prefers_system_industry_mapping():
    fake_db = Mock()
    fake_db.stock_basic_info.find_one = AsyncMock(return_value=None)
    fake_db.stock_basic_info.update_one = AsyncMock(return_value=Mock())

    request = SingleStockSyncRequest(
        symbol="300750",
        sync_realtime=False,
        sync_historical=False,
        sync_financial=False,
        sync_basic=True,
        data_source="akshare",
    )

    with patch("app.routers.stock_sync.get_mongo_db", return_value=fake_db), \
         patch("app.routers.stock_sync.get_akshare_sync_service", new=AsyncMock(side_effect=_fake_get_akshare_sync_service)), \
         patch("app.services.official_industry_service.fetch_industry_mapping", new=AsyncMock(return_value={"300750": "Electrical equipment"})):
        response = __import__("asyncio").run(
            sync_single_stock(request, BackgroundTasks(), current_user={"id": "u1"})
        )

    assert response["success"] is True
    assert response["data"]["basic_sync"]["success"] is True
    update_payload = fake_db.stock_basic_info.update_one.await_args.args[1]["$set"]
    assert update_payload["industry"] == "Electrical equipment"
    assert update_payload["industry_source"] == "system_industry_mapping"

# === Merged from test_toolkit_news_split_bridge.py ===
def test_toolkit_exposes_split_news_tools_for_legacy_workflow():
    from tradingagents.agents.utils.agent_utils import Toolkit

    toolkit = Toolkit()

    assert hasattr(toolkit, "get_stock_news_headlines_unified")
    assert hasattr(toolkit, "get_stock_news_details_unified")
    assert hasattr(toolkit.get_stock_news_headlines_unified, "invoke")
    assert hasattr(toolkit.get_stock_news_details_unified, "invoke")

# === Merged from test_unified_dataframe.py ===
import pandas as pd
from unittest import mock

from tradingagents.dataflows.unified_dataframe import get_china_daily_df_unified


def test_unified_dataframe_prefers_tushare_then_akshare_then_baostock():
    # Simulate three sources: tushare succeeds, last two should not be called
    with mock.patch('tradingagents.dataflows.unified_dataframe.get_tushare_adapter') as m_ts, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_akshare_provider') as m_ak, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_baostock_provider') as m_bs, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_data_source_manager') as m_dsm:

        df_ts = pd.DataFrame({
            'Open':[1,2], 'High':[2,3], 'Low':[0.5,1.5], 'Close':[1.5,2.5], 'Volume':[100,200], 'Amount':[150,500], 'trade_date':['2024-01-01','2024-01-02']
        })
        m_ts.return_value.get_stock_data.return_value = df_ts
        m_ak.return_value.get_stock_data.return_value = pd.DataFrame()
        m_bs.return_value.get_stock_data.return_value = pd.DataFrame()

        # The current source is tushare
        m_dsm.return_value.current_source.value = 'tushare'
        m_dsm.return_value.available_sources = []

        df = get_china_daily_df_unified('000001', '2024-01-01', '2024-01-31')
        assert not df.empty
        assert 'close' in df.columns  # Standardized
        assert df.shape[0] == 2


def test_unified_dataframe_fallback_to_baostock_when_others_fail():
    with mock.patch('tradingagents.dataflows.unified_dataframe.get_tushare_adapter') as m_ts, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_akshare_provider') as m_ak, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_baostock_provider') as m_bs, \
         mock.patch('tradingagents.dataflows.unified_dataframe.get_data_source_manager') as m_dsm:

        m_ts.return_value.get_stock_data.return_value = pd.DataFrame()
        m_ak.return_value.get_stock_data.return_value = pd.DataFrame()
        df_bs = pd.DataFrame({
            'date':['2024-01-01','2024-01-02'], 'code':['sz.000001','sz.000001'],
            'open':[1,2], 'high':[2,3], 'low':[0.5,1.5], 'close':[1.5,2.5], 'volume':[100,200], 'amount':[150,500]
        })
        m_bs.return_value.get_stock_data.return_value = df_bs

        m_dsm.return_value.current_source.value = 'tushare'
        m_dsm.return_value.available_sources = ['akshare','baostock']

        df = get_china_daily_df_unified('000001', '2024-01-01', '2024-01-31')
        assert not df.empty
        assert 'close' in df.columns
        assert df.iloc[0]['close'] == 1.5

