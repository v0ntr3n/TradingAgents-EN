from __future__ import annotations

# === Merged from test_agent_api_available_filter.py ===
from core.agents.config import AgentCategory, AgentMetadata, LicenseTier
from core.api.agent_api import AgentAPI


class _StubRegistry:
    def __init__(self, items):
        self._items = items

    def list_all(self):
        return list(self._items)

    def list_by_category(self, category):
        category_value = category.value if hasattr(category, 'value') else category
        return [
            item for item in self._items
            if (item.category.value if hasattr(item.category, 'value') else item.category) == category_value
        ]


def test_list_available_for_tier_excludes_unmaintained_agents() -> None:
    legacy_agent = AgentMetadata(
        id="market_analyst",
        name="market analyst",
        description="legacy",
        category=AgentCategory.ANALYST,
        version="1.0.0",
        license_tier=LicenseTier.FREE,
    )
    free_v2_agent = AgentMetadata(
        id="market_analyst_v2",
        name="market analyst v2.0",
        description="maintained free",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
    )
    pro_v2_agent = AgentMetadata(
        id="sector_analyst_v2",
        name="Sector Analyst v2.0",
        description="maintained pro",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.PRO,
    )

    api = AgentAPI.__new__(AgentAPI)
    api._registry = _StubRegistry([legacy_agent, free_v2_agent, pro_v2_agent])

    agents = api.list_available_for_tier("free")
    agent_ids = [agent["id"] for agent in agents]

    assert agent_ids == ["market_analyst_v2", "sector_analyst_v2"]
    assert all(agent["maintenance_status"] == "maintained" for agent in agents)

    free_agent = next(agent for agent in agents if agent["id"] == "market_analyst_v2")
    pro_agent = next(agent for agent in agents if agent["id"] == "sector_analyst_v2")

    assert free_agent["is_available"] is True
    assert "locked_reason" not in free_agent
    assert pro_agent["is_available"] is False
    assert pro_agent["locked_reason"] == "Requires advanced student permissions"


def test_get_categories_counts_only_maintained_agents() -> None:
    legacy_agent = AgentMetadata(
        id="market_analyst",
        name="market analyst",
        description="legacy",
        category=AgentCategory.ANALYST,
        version="1.0.0",
        license_tier=LicenseTier.FREE,
    )
    maintained_analyst = AgentMetadata(
        id="market_analyst_v2",
        name="market analyst v2.0",
        description="maintained",
        category=AgentCategory.ANALYST,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
    )
    maintained_manager = AgentMetadata(
        id="research_manager_v2",
        name="research manager v2.0",
        description="maintained",
        category=AgentCategory.MANAGER,
        version="2.0.0",
        license_tier=LicenseTier.FREE,
    )

    api = AgentAPI.__new__(AgentAPI)
    api._registry = _StubRegistry([legacy_agent, maintained_analyst, maintained_manager])

    categories = {item["id"]: item["count"] for item in api.get_categories()}

    assert categories["analyst"] == 1
    assert categories["manager"] == 1

# === Merged from test_binding_manager_tool_normalization.py ===
class _FakeToolAgentBindingsCollection:
    def __init__(self, docs):
        self._docs = list(docs)

    def find(self, query, sort=None):
        agent_id = query.get("agent_id")
        docs = [
            doc
            for doc in self._docs
            if doc.get("agent_id") == agent_id and doc.get("is_active", True) is not False
        ]
        if sort:
            for field_name, direction in reversed(sort):
                docs.sort(key=lambda item: item.get(field_name, 0), reverse=direction < 0)
        return docs


class _FakeDb:
    def __init__(self, docs):
        self.tool_agent_bindings = _FakeToolAgentBindingsCollection(docs)


def test_binding_manager_rewrites_news_analyst_v2_legacy_bindings():
    from core.config.binding_manager import BindingManager

    manager = BindingManager()
    manager.set_database(
        _FakeDb(
            [
                {"agent_id": "news_analyst_v2", "tool_id": "get_weather", "priority": 200},
                {"agent_id": "news_analyst_v2", "tool_id": "get_stock_news_unified", "priority": 100},
            ]
        )
    )

    try:
        tools = manager.get_tools_for_agent("news_analyst_v2")
    finally:
        manager.set_database(None)

    assert tools == [
        "get_stock_news_headlines_unified",
        "get_stock_news_details_unified",
    ]


def test_binding_manager_preserves_valid_extra_tools_while_migrating_news_bindings():
    from core.config.binding_manager import BindingManager

    manager = BindingManager()
    manager.set_database(
        _FakeDb(
            [
                {"agent_id": "news_analyst_v2", "tool_id": "get_stock_news_headlines_unified", "priority": 300},
                {"agent_id": "news_analyst_v2", "tool_id": "get_stock_news_unified", "priority": 100},
            ]
        )
    )

    try:
        tools = manager.get_tools_for_agent("news_analyst_v2")
    finally:
        manager.set_database(None)

    assert tools == [
        "get_stock_news_headlines_unified",
        "get_stock_news_details_unified",
    ]

# === Merged from test_builder_llm_selection.py ===
from types import SimpleNamespace

from core.workflow.builder import LegacyDependencyProvider, WorkflowBuilder, _select_llm_type_for_agent


def test_index_and_sector_v2_agents_use_deep_llm() -> None:
    assert _select_llm_type_for_agent("index_analyst_v2") == "deep"
    assert _select_llm_type_for_agent("sector_analyst_v2") == "deep"


def test_managers_stay_on_deep_llm() -> None:
    assert _select_llm_type_for_agent("research_manager_v2") == "deep"
    assert _select_llm_type_for_agent("risk_manager_v2") == "deep"


def test_regular_analysts_stay_on_quick_llm() -> None:
    assert _select_llm_type_for_agent("market_analyst_v2") == "quick"
    assert _select_llm_type_for_agent("fundamentals_analyst_v2") == "quick"


def test_custom_llm_respects_agent_timeout_and_max_tokens(monkeypatch) -> None:
    captured = {}

    def fake_get_provider_and_url_by_model_sync(model: str):
        return {
            "provider": "dashscope",
            "backend_url": "https://example.com/v1",
            "api_key": "db-key",
        }

    def fake_create_llm_by_provider(**kwargs):
        captured.update(kwargs)
        return kwargs

    monkeypatch.setattr(
        "app.services.simple_analysis_service.get_provider_and_url_by_model_sync",
        fake_get_provider_and_url_by_model_sync,
    )
    monkeypatch.setattr(
        "tradingagents.graph.trading_graph.create_llm_by_provider",
        fake_create_llm_by_provider,
    )

    provider = LegacyDependencyProvider(
        {
            "quick_think_llm": "qwen3.5-plus",
            "quick_timeout": 60,
            "quick_max_tokens": 2000,
        }
    )

    llm = provider.get_llm("quick", temperature=0.6, timeout=120, max_tokens=3200)

    assert llm["temperature"] == 0.6
    assert llm["timeout"] == 120
    assert llm["max_tokens"] == 3200
    assert captured["model"] == "qwen3.5-plus"


def test_workflow_builder_passes_agent_llm_overrides(monkeypatch) -> None:
    from core.agents import AgentConfig

    captured = {}

    builder = WorkflowBuilder.__new__(WorkflowBuilder)
    builder.registry = SimpleNamespace(is_registered=lambda agent_id: True)
    builder.factory = SimpleNamespace(create=lambda *args, **kwargs: SimpleNamespace())
    builder.default_config = AgentConfig()
    builder.binding_manager = SimpleNamespace(get_tools_for_node=lambda **kwargs: [])
    builder.agent_config_manager = SimpleNamespace(
        get_agent_config=lambda agent_id: {
            "config": {
                "temperature": 0.6,
                "timeout": 180,
                "max_tokens": 3200,
            }
        }
    )
    builder.memory_manager = None
    builder.llm_override = None
    builder._agents = {}
    builder._workflow_id = "wf-test"
    builder._has_agent_config_in_db = lambda agent_id: False
    builder._ensure_workflow_surface_access = lambda agent_id, db_agent_config=None: None
    builder._resolve_agent_output_field = lambda *args, **kwargs: None
    builder._execute_agent_node_with_runtime = lambda **kwargs: kwargs
    builder._legacy_provider = SimpleNamespace(
        get_llm=lambda llm_type, temperature=None, timeout=None, max_tokens=None: captured.update(
            {
                "llm_type": llm_type,
                "temperature": temperature,
                "timeout": timeout,
                "max_tokens": max_tokens,
            }
        ) or SimpleNamespace(),
        get_toolkit=lambda: None,
    )

    node = SimpleNamespace(
        id="risk-node",
        type="risk",
        agent_id="risky_analyst_v2",
        label="risk analysis",
        config={},
    )

    builder._create_agent_node(node)

    assert captured == {
        "llm_type": "deep",
        "temperature": 0.6,
        "timeout": 180,
        "max_tokens": 3200,
    }

# === Merged from test_index_analyst_v2_cache.py ===
from unittest.mock import Mock


def test_index_cache_identity_keeps_requested_and_effective_dates_separate(monkeypatch):
    from core.agents.adapters import index_analyst_v2 as module

    monkeypatch.setattr(module, "apply_stable_data_cutoff", lambda date_str, cutoff_hour=19: "2026-04-20")

    symbol, trade_date, effective_date = module._build_index_cache_identity("2026-04-21")

    assert trade_date == "2026-04-21"
    assert effective_date == "2026-04-20"
    assert symbol == "market_v2__req_20260421__eff_20260420"


def test_get_cached_index_report_uses_effective_date_in_cache_symbol(monkeypatch):
    from core.agents.adapters import index_analyst_v2 as module

    cache = Mock()
    cache.find_cached_analysis_report.return_value = None

    monkeypatch.setattr(module, "_get_cache_manager", lambda: cache)
    monkeypatch.setattr(module, "apply_stable_data_cutoff", lambda date_str, cutoff_hour=19: "2026-04-20")

    module._get_cached_index_report("2026-04-21")

    cache.find_cached_analysis_report.assert_called_once_with(
        report_type="index_report",
        symbol="market_v2__req_20260421__eff_20260420",
        trade_date="2026-04-21",
        max_age_hours=1,
    )


def test_save_index_report_to_cache_uses_effective_date_in_cache_symbol(monkeypatch):
    from core.agents.adapters import index_analyst_v2 as module

    cache = Mock()
    monkeypatch.setattr(module, "_get_cache_manager", lambda: cache)
    monkeypatch.setattr(module, "apply_stable_data_cutoff", lambda date_str, cutoff_hour=19: "2026-04-20")

    saved = module._save_index_report_to_cache("2026-04-21", "x" * 120)

    assert saved is True
    cache.save_analysis_report.assert_called_once_with(
        report_type="index_report",
        report_data="x" * 120,
        symbol="market_v2__req_20260421__eff_20260420",
        trade_date="2026-04-21",
    )

# === Merged from test_llm_provider_api_key_passthrough.py ===
from tradingagents.graph.trading_graph import create_llm_by_provider
import tradingagents.llm_adapters.openai_compatible_base as base_module


def test_create_llm_by_provider_passes_api_key_to_custom_openai(monkeypatch):
    captured = {}

    def fake_create_openai_compatible_llm(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(base_module, "create_openai_compatible_llm", fake_create_openai_compatible_llm)

    create_llm_by_provider(
        provider="custom_openai",
        model="qwen3.5-plus",
        backend_url="https://example.com/v1",
        temperature=0.2,
        max_tokens=4000,
        timeout=180,
        api_key="sk-test-custom-openai-key",
    )

    assert captured["provider"] == "custom_openai"
    assert captured["api_key"] == "sk-test-custom-openai-key"


def test_create_llm_by_provider_passes_api_key_to_qianfan(monkeypatch):
    captured = {}

    def fake_create_openai_compatible_llm(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(base_module, "create_openai_compatible_llm", fake_create_openai_compatible_llm)

    create_llm_by_provider(
        provider="qianfan",
        model="ERNIE-Speed-8K",
        backend_url="https://example.com/v2",
        temperature=0.2,
        max_tokens=4000,
        timeout=180,
        api_key="bce-v3/test-ak/test-sk",
    )

    assert captured["provider"] == "qianfan"
    assert captured["api_key"] == "bce-v3/test-ak/test-sk"


def test_create_openai_compatible_llm_forces_kimi_temperature(monkeypatch):
    captured = {}

    class FakeAdapter:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(
        base_module.OPENAI_COMPATIBLE_PROVIDERS["custom_openai"],
        "adapter_class",
        FakeAdapter,
    )

    base_module.create_openai_compatible_llm(
        provider="custom_openai",
        model="kimi-k2.5",
        base_url="https://api.moonshot.cn/v1",
        temperature=0.2,
        max_tokens=4000,
    )

    assert captured["temperature"] == 1.0


def test_create_llm_by_provider_forces_kimi_temperature(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("tradingagents.graph.trading_graph.ChatOpenAI", FakeChatOpenAI)

    create_llm_by_provider(
        provider="kimi",
        model="kimi-k2.5",
        backend_url="https://api.moonshot.cn/v1",
        temperature=0.2,
        max_tokens=4000,
        timeout=180,
        api_key="sk-test-kimi-key",
    )

    assert captured["temperature"] == 1.0

# === Merged from test_standard_prompt_footer.py ===
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_all_export_templates_include_standard_prompt_footer() -> None:
    templates = json.loads((ROOT / "exports" / "current_db_templates.json").read_text(encoding="utf-8"))

    checked = 0
    for item in templates:
        content = item.get("content")
        if not isinstance(content, dict) or "system_prompt" not in content:
            continue

        checked += 1
        system_prompt = str(content.get("system_prompt") or "")
        assert "Please use Chinese and conduct analysis based on real data." in system_prompt
        assert "This analysis report is for reference only and does not constitute investment advice." in system_prompt

    assert checked > 0


def test_all_export_templates_have_single_disclaimer_block() -> None:
    templates = json.loads((ROOT / "exports" / "current_db_templates.json").read_text(encoding="utf-8"))

    checked = 0
    for item in templates:
        content = item.get("content")
        if not isinstance(content, dict) or "system_prompt" not in content:
            continue

        checked += 1
        system_prompt = str(content.get("system_prompt") or "")
        assert system_prompt.count("**Disclaimer**") == 1
        assert system_prompt.count("This analysis report is for reference only and does not constitute investment advice.") == 1

    assert checked > 0

# === Merged from test_trading_graph_memory_provider.py ===
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph import trading_graph as trading_graph_module


class _DummyLLM:
    pass


class _FakeMemoryProvider:
    def __init__(self, config=None, memory_enabled=True):
        self.config = config or {}
        self.memory_enabled = memory_enabled
        self.requested = []

    def get_memory(self, memory_name):
        self.requested.append(memory_name)
        return {"memory_name": memory_name}


class _FakeGraphSetup:
    last_init_args = None

    def __init__(self, *args):
        _FakeGraphSetup.last_init_args = args

    def setup_graph(self, selected_analysts):
        return {"selected_analysts": selected_analysts}


class _FakeConditionalLogic:
    def __init__(self, max_debate_rounds=1, max_risk_discuss_rounds=1):
        self.max_debate_rounds = max_debate_rounds
        self.max_risk_discuss_rounds = max_risk_discuss_rounds


def test_trading_graph_initializes_memories_via_memory_provider(monkeypatch):
    fake_provider = _FakeMemoryProvider()

    monkeypatch.setattr(trading_graph_module, "set_config", lambda config: None)
    monkeypatch.setattr(trading_graph_module.os, "makedirs", lambda *args, **kwargs: None)
    monkeypatch.setattr(trading_graph_module, "ChatOpenAI", lambda *args, **kwargs: _DummyLLM())
    monkeypatch.setattr(trading_graph_module, "Toolkit", lambda config=None: object())
    monkeypatch.setattr(trading_graph_module.TradingAgentsGraph, "_create_tool_nodes", lambda self: {})
    monkeypatch.setattr(trading_graph_module, "MemoryProvider", lambda config=None, memory_enabled=True: fake_provider)
    monkeypatch.setattr(trading_graph_module, "GraphSetup", _FakeGraphSetup)
    monkeypatch.setattr(trading_graph_module, "ConditionalLogic", _FakeConditionalLogic)
    monkeypatch.setattr(trading_graph_module, "Reflector", lambda llm: object())
    monkeypatch.setattr(trading_graph_module, "SignalProcessor", lambda llm: object())

    config = DEFAULT_CONFIG.copy()
    config.update(
        {
            "llm_provider": "openai",
            "backend_url": "https://example.test/v1",
            "deep_think_llm": "deep-model",
            "quick_think_llm": "quick-model",
            "memory_enabled": True,
        }
    )

    graph = trading_graph_module.TradingAgentsGraph(selected_analysts=["market"], config=config)

    assert fake_provider.requested == [
        "bull_memory",
        "bear_memory",
        "trader_memory",
        "invest_judge_memory",
        "risk_manager_memory",
    ]
    assert graph.bull_memory == {"memory_name": "bull_memory"}
    assert graph.risk_manager_memory == {"memory_name": "risk_manager_memory"}
    assert _FakeGraphSetup.last_init_args[4] == {"memory_name": "bull_memory"}
    assert _FakeGraphSetup.last_init_args[8] == {"memory_name": "risk_manager_memory"}

# === Merged from test_tradingagents_runtime_settings.py ===
import os
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Routers
from app.routers import config as config_router
from app.routers.auth_db import get_current_user


def _admin_user():
    return {"id": "u1", "is_admin": True}


@pytest.fixture()
def app_client_config():
    app = FastAPI()
    app.include_router(config_router.router, prefix="/api")
    app.dependency_overrides[get_current_user] = _admin_user
    return TestClient(app)


def test_config_settings_contains_ta_keys(app_client_config: TestClient, monkeypatch):
    # Mock provider to return TA keys without hitting DB
    from app.services import config_provider as cfgprov

    async def _fake_eff():
        return {
            "ta_us_min_api_interval_seconds": 0.25,
            "ta_google_news_sleep_min_seconds": 1.5,
        }

    monkeypatch.setattr(cfgprov.provider, "get_effective_system_settings", _fake_eff)

    resp = app_client_config.get("/api/config/settings")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert "ta_us_min_api_interval_seconds" in data
    assert data["ta_us_min_api_interval_seconds"] == 0.25
    assert data["ta_google_news_sleep_min_seconds"] == 1.5


def test_runtime_settings_priority_db_env_default(monkeypatch):
    # Ensure ENV is set
    monkeypatch.setenv("TA_US_MIN_API_INTERVAL_SECONDS", "3.0")

    # Monkeypatch provider to simulate DB value
    from app.services import config_provider as cfgprov
    from tradingagents.config import runtime_settings as rs

    async def _fake_eff_db():
        return {"ta_us_min_api_interval_seconds": 0.25}

    monkeypatch.setattr(cfgprov.provider, "get_effective_system_settings", _fake_eff_db)

    # DB should override ENV and default
    v_db = rs.get_float("TA_US_MIN_API_INTERVAL_SECONDS", "ta_us_min_api_interval_seconds", 1.0)
    assert abs(v_db - 0.25) < 1e-9

    # If DB doesn't provide the key, ENV should override default
    async def _fake_eff_empty():
        return {}

    monkeypatch.setattr(cfgprov.provider, "get_effective_system_settings", _fake_eff_empty)
    v_env = rs.get_float("TA_US_MIN_API_INTERVAL_SECONDS", "ta_us_min_api_interval_seconds", 1.0)
    assert abs(v_env - 3.0) < 1e-9

    # If ENV is absent too, fall back to default
    monkeypatch.delenv("TA_US_MIN_API_INTERVAL_SECONDS", raising=False)
    v_def = rs.get_float("TA_US_MIN_API_INTERVAL_SECONDS", "ta_us_min_api_interval_seconds", 1.0)
    assert abs(v_def - 1.0) < 1e-9

