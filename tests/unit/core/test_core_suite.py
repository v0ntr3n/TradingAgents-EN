from __future__ import annotations

# === Merged from test_assistant_fast_search_skill_routing.py ===
# -*- coding: utf-8 -*-
"""Recent search fast path vs user generated external skill routing give way test.

Background (Real Flaw): A user asked Ask about the sales changes of various models in the industry in the past six months , and was answered by the stock era
Keywords fast path ("Recently"+"change") Hijack go to web search before LLM tool selection,
The installed sales skill of Knowing Car Emperor has no chance to appear at all.

Repair: After the fast path hits the keyword, first use the registry source=generated Skill metadata
Make way for data-driven domain word matching if it can be taken over by a dedicated Skill.
"""

from types import SimpleNamespace
from unittest.mock import patch

from app.services.intelligent_assistant_service import (
    _domain_terms,
    _matches_generated_skill,
    _should_use_recent_search,
)


def _skill(tool_id, name, description, when_to_use="", fc_enabled=True):
    return SimpleNamespace(
        id=tool_id,
        name=name,
        description=description,
        when_to_use=when_to_use,
        fc_enabled=fc_enabled,
    )


_DCD_SKILL = _skill(
    "dongchedi_car_monthly_sales_rank",
    "Inquiry on the national monthly sales list of Undercardi",
    "Call the National Chedi National Monthly Sales List interface to obtain vehicle model sales data by month, list type and other parameters."
    "It also supports filtering monthly sales of each vehicle model by brand (such as Wenjie).",
)


class TestDomainTerms:
    def test_extracts_chinese_bigrams_and_english_tokens(self):
        terms = _domain_terms("Wenjie M9 model sales")
        assert "Ask the world" in terms
        assert "car model" in terms
        assert "Sales volume" in terms
        assert "m9" in terms

    def test_stopgrams_removed(self):
        terms = _domain_terms("Sales data interface")
        assert "Sales volume" in terms
        assert "data" not in terms
        assert "interface" not in terms


class TestGeneratedSkillRouting:
    def _registry(self, skills):
        reg = SimpleNamespace(get_external_skills=lambda: skills)
        return patch("core.tools.get_tool_registry", lambda: reg)

    def test_dongchedi_sales_question_bypasses_fast_search(self):
        """Real Accident Sentence: You must hit the car-savvy Skill and give way to the fast path"""
        # First confirm that the sentence itself will hit the old fast path keyword (otherwise the test is meaningless)
        msg = "Please help me check the sales changes of various models in the industry in the past six months."
        assert _should_use_recent_search(msg)

        with self._registry([_DCD_SKILL]):
            hit = _matches_generated_skill(msg)
        assert hit is not None
        assert hit[0] == "dongchedi_car_monthly_sales_rank"

    def test_stock_holding_question_still_uses_fast_search(self):
        """Original stock scenario: There is no domain overlap with the external Skill and should not give way."""
        msg = "Berkshire Hathaway s latest shareholding changes"
        assert _should_use_recent_search(msg)
        with self._registry([_DCD_SKILL]):
            assert _matches_generated_skill(msg) is None

    def test_single_overlap_not_enough(self):
        """The co-occurrence of only one domain word is not counted as a hit (to prevent misjudgment of accidental co-occurrence)"""
        # Contains only one field intersection word "sales"
        skill = _skill("x", "A certain list", "Count sales of a product")
        with self._registry([skill]):
            # ""Recent Sales"——Only with this skill"Sales volume"an intersection
            assert _matches_generated_skill("How sales have changed recently") is None

    def test_disabled_skill_ignored(self):
        disabled = _skill("x", "Understand car sales", "Ask the world s car sales", fc_enabled=False)
        with self._registry([disabled]):
            assert _matches_generated_skill("Recent sales changes of Wenjie models") is None

    def test_no_external_skills_returns_none(self):
        with self._registry([]):
            assert _matches_generated_skill("Recent sales changes of Wenjie models") is None

    def test_generic_non_sales_question_not_routed_to_dcd(self):
        """Even if a purely news/announcement question mentions the recent past, it should not be mistakenly caught by domain matching."""
        msg = "Are there any new announcements recently?"
        with self._registry([_DCD_SKILL]):
            assert _matches_generated_skill(msg) is None

# === Merged from test_base_agent_tool_calls.py ===
from langchain_core.tools import StructuredTool

from core.agents.base import BaseAgent
from core.agents.config import AgentCategory, AgentConfig, AgentInput, AgentMetadata, AgentOutput, LicenseTier


class _DummyAgent(BaseAgent):
    metadata = AgentMetadata(
        id="dummy_agent",
        name="Dummy Agent",
        description="test agent",
        category=AgentCategory.ANALYST,
        license_tier=LicenseTier.FREE,
        inputs=[AgentInput(name="ticker", type="string", description="ticker")],
        outputs=[AgentOutput(name="report", type="string", description="report")],
        tools=[],
        default_tools=[],
    )

    def analyze(self, *args, **kwargs):
        raise NotImplementedError()

    def execute(self, state):
        return state


def test_execute_tool_calls_unwraps_nested_kwargs_for_langchain_tool():
    received = {}

    def analyze_a_share_dupont(symbol: str, periods: int = 8) -> str:
        received["symbol"] = symbol
        received["periods"] = periods
        return f"symbol={symbol},periods={periods}"

    agent = _DummyAgent(config=AgentConfig(), llm=None, tool_ids=None)
    agent._langchain_tools = [
        StructuredTool.from_function(
            func=analyze_a_share_dupont,
            name="analyze_a_share_dupont",
            description="dupont",
        )
    ]

    messages = agent._execute_tool_calls([
        {
            "id": "call-1",
            "name": "analyze_a_share_dupont",
            "args": {
                "kwargs": {
                    "symbol": "600519.SH",
                    "periods": 4,
                }
            },
        }
    ])

    assert len(messages) == 1
    assert received == {"symbol": "600519", "periods": 4}
    assert messages[0].content == "symbol=600519,periods=4"

# === Merged from test_deprecations.py ===
import importlib
import warnings


def test_legacy_env_aliases_map_to_new(monkeypatch):
    # Ensure new keys are not set so aliasing triggers
    monkeypatch.delenv("HOST", raising=False)
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("DEBUG", raising=False)

    # Set only legacy keys
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    monkeypatch.setenv("API_PORT", "8123")
    monkeypatch.setenv("API_DEBUG", "false")

    # Reload module under warning capture to assert deprecation warnings
    import app.core.config as cfg
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always", DeprecationWarning)
        importlib.reload(cfg)

    # At least one deprecation warning should be emitted
    assert any(isinstance(x.message, DeprecationWarning) for x in w), "No DeprecationWarning captured"

    # Verify values are mapped correctly
    s = cfg.Settings()
    assert s.HOST == "127.0.0.1"
    assert s.PORT == 8123
    assert s.DEBUG is False


# === Merged from test_dupont_external_skill_template.py ===
import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "external_skill_templates" / "dupont_analysis_skill.py"
MODULE_SPEC = importlib.util.spec_from_file_location("dupont_analysis_skill", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
dupont_skill = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(dupont_skill)


def test_analyze_a_share_dupont_uses_average_bases_and_quarter_annualization(monkeypatch):
    monkeypatch.setattr(
        dupont_skill,
        "get_stock_basic_info",
        lambda symbol: {"name": "testing company", "industry": "Liquor"},
    )
    monkeypatch.setattr(
        dupont_skill,
        "get_stock_financial_periods",
        lambda symbol, limit=8: [
            {
                "report_period": "20240930",
                "roe": 24.0,
                "netprofit_margin": 30.0,
                "gross_margin": 60.0,
                "revenue": 300.0,
                "total_assets": 1000.0,
                "total_equity": 500.0,
            },
            {
                "report_period": "20240630",
                "roe": 20.0,
                "netprofit_margin": 28.0,
                "gross_margin": 58.0,
                "revenue": 180.0,
                "total_assets": 900.0,
                "total_equity": 450.0,
            },
        ],
    )

    result = dupont_skill.analyze_a_share_dupont("600519", periods=2)

    latest = result["latest_dupont"]
    assert latest["annualization_factor"] == 4.0 / 3.0
    assert latest["average_total_assets"] == 950.0
    assert latest["average_total_equity"] == 475.0
    assert round(latest["asset_turnover"], 6) == round((300.0 * (4.0 / 3.0)) / 950.0, 6)
    assert round(latest["equity_multiplier"], 6) == round(950.0 / 475.0, 6)


def test_analyze_a_share_dupont_preserves_zero_values(monkeypatch):
    monkeypatch.setattr(
        dupont_skill,
        "get_stock_basic_info",
        lambda symbol: {"name": "testing company", "industry": "Manufacturing"},
    )
    monkeypatch.setattr(
        dupont_skill,
        "get_stock_financial_periods",
        lambda symbol, limit=8: [
            {
                "report_period": "20241231",
                "roe": 0.0,
                "netprofit_margin": 0.0,
                "gross_margin": 0.0,
                "revenue": 0.0,
                "total_assets": 1000.0,
                "total_equity": 400.0,
            },
            {
                "report_period": "20240930",
                "roe": 1.0,
                "netprofit_margin": 2.0,
                "gross_margin": 3.0,
                "revenue": 10.0,
                "total_assets": 900.0,
                "total_equity": 350.0,
            },
        ],
    )

    result = dupont_skill.analyze_a_share_dupont("600519", periods=2)
    latest = result["latest_dupont"]

    assert latest["roe_percent"] == 0.0
    assert latest["net_margin_percent"] == 0.0
    assert latest["gross_margin_percent"] == 0.0
    assert latest["asset_turnover"] == 0.0

# === Merged from test_embedding_manager_db_proxy.py ===
from core.llm.embedding_manager import EmbeddingManager


class _BrokenAsyncCollection:
    def find_one(self, *args, **kwargs):
        raise AssertionError("should not use async/proxy collections directly")

    def find(self, *args, **kwargs):
        raise AssertionError("should not use async/proxy collections directly")


class _BrokenProxyDb:
    llm_providers = _BrokenAsyncCollection()
    system_configs = _BrokenAsyncCollection()


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def __iter__(self):
        return iter(self._docs)


class _FakeCollection:
    def __init__(self, docs=None, one=None):
        self._docs = docs or []
        self._one = one

    def find_one(self, *args, **kwargs):
        return self._one

    def find(self, *args, **kwargs):
        return _FakeCursor(self._docs)


class _FakeSyncDb:
    def __init__(self):
        self.system_configs = _FakeCollection(
            one={
                "is_active": True,
                "system_settings": {
                    "default_embedding_model": "dashscope:text-embedding-v3"
                },
            }
        )
        self.llm_providers = _FakeCollection(
            docs=[
                {
                    "name": "dashscope",
                    "display_name": "Alibaba Cloud Tongyi Qianwen",
                    "api_key": "test-key",
                    "default_base_url": "https://dashscope.aliyuncs.com/api/v1",
                    "embedding_model": "text-embedding-v3",
                    "supported_features": ["embedding"],
                    "is_active": True,
                }
            ]
        )


def test_embedding_manager_uses_sync_db_for_proxy_objects(monkeypatch):
    fake_sync_db = _FakeSyncDb()

    monkeypatch.setattr(
        "app.core.database.get_mongo_db_sync",
        lambda: fake_sync_db,
    )

    manager = EmbeddingManager(db=_BrokenProxyDb())

    assert len(manager._providers) == 1
    assert manager._primary_provider is not None
    assert manager._primary_provider["name"] == "dashscope"
    assert manager._primary_provider["model"] == "text-embedding-v3"

# === Merged from test_eval_result_realtime.py ===
# -*- coding: utf-8 -*-
"""Quality assessment results are displayed in real time — Unit testing

Coverage:
1. EvalScore.expert_comment Field parsing and filling (output_evaluator)
2. IterationController._build_eval_result_extra Event structure (including total/passed)
3. service Progress callback extra transparent transmission (_progress_cb is written to pipeline_eval_result)
"""
import re

from core.tools.external.iteration_controller import IterationController
from core.tools.external.skill_spec import EvalScore


def test_eval_score_has_expert_comment_default_empty():
    score = EvalScore()
    assert score.expert_comment == ""
    assert score.total >= 0


def test_build_eval_result_extra_contains_total_and_passed():
    # weighted total score = 0.25*9 + 0.25*9 + 0.20*8 + 0.20*8 + 0.10*9 = 8.6 >= threshold 8.5
    score = EvalScore(
        executability=9, authenticity=9, completeness=8, relevance=8, format_quality=9,
        expert_comment="Overall quality is good, data link is clear",
    )
    extra = IterationController._build_eval_result_extra(score, round_num=2)

    assert "eval_result" in extra
    data = extra["eval_result"]
    # total Yes @property, Must be brought out explicitly
    assert data["total"] == score.total
    assert data["round"] == 2
    assert data["passed"] is True
    assert data["expert_comment"] == "Overall quality is good, data link is clear"
    # Five dimensions fully revealed
    for key in ("executability", "authenticity", "completeness", "relevance", "format_quality"):
        assert key in data


def test_build_eval_result_extra_passed_false_below_threshold():
    score = EvalScore(executability=6.0)
    extra = IterationController._build_eval_result_extra(score, round_num=1)
    assert extra["eval_result"]["passed"] is False


def test_evaluator_parses_expert_comment_from_verdict():
    """from <verdict> JSON Parse expert_comment and write it EvalScore"""
    raw = (
        '<verdict>\n{"executability": 9, "authenticity": 8, "completeness": 8, '
        '"relevance": 9, "format_quality": 8, "expert_comment": "The data is real and the structure is clear"}\n</verdict>'
    )
    match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", raw, re.DOTALL)
    assert match

    import json as _json
    scores = _json.loads(match.group(1).strip())
    score = EvalScore()
    score.executability = float(scores["executability"])
    score.authenticity = float(scores["authenticity"])
    score.completeness = float(scores["completeness"])
    score.relevance = float(scores["relevance"])
    score.format_quality = float(scores["format_quality"])
    comment = str(scores.get("expert_comment", "")).strip()
    if comment:
        score.expert_comment = comment

    assert score.expert_comment == "The data is real and the structure is clear"
    assert score.executability == 9.0

# === Merged from test_evaluate_memory_recall_quality.py ===
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "evaluate_memory_recall_quality.py"

spec = importlib.util.spec_from_file_location("evaluate_memory_recall_quality", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_evaluate_all_scenarios_passes() -> None:
    summary = module.evaluate_all_scenarios()

    assert summary["ok"] is True
    assert summary["passed"] == summary["total"]
    assert summary["total"] >= 3


def test_assistant_scenario_prefers_user_preference_scope() -> None:
    scenario = module._assistant_scenario()
    result = module._evaluate_scenario(scenario)

    assert result["ok"] is True
    assert result["first_scope"] == "user_preference"
    assert result["deduped_count"] == 3


def test_skill_generation_scenario_dedupes_duplicate_lessons() -> None:
    scenario = module._skill_generation_scenario()
    result = module._evaluate_scenario(scenario)

    assert result["ok"] is True
    assert result["deduped_count"] == 2
    assert any(" [Historical Lessons]" in line for line in result["formatted_preview"])


def test_agent_builder_scenario_prefers_spec_matched_lessons() -> None:
    scenario = module._agent_builder_scenario()
    result = module._evaluate_scenario(scenario)

    assert result["ok"] is True
    assert result["first_scope"] == "agent_builder_lesson"
    assert result["deduped_count"] == 3
    assert any(" [History Workshop Lessons]" in line for line in result["formatted_preview"])

# === Merged from test_external_skill_langchain_schema.py ===
from core.tools.config import ToolCategory, ToolMetadata, ToolParameter
from core.tools.registry import ToolRegistry


def test_generated_external_skill_uses_parameter_schema_for_dict_invoke():
    registry = ToolRegistry()
    tool_id = "test_external_dupont_schema"

    def external_skill_wrapper(**kwargs):
        symbol = kwargs["symbol"]
        periods = kwargs.get("periods", 8)
        return f"symbol={symbol},periods={periods}"

    metadata = ToolMetadata(
        id=tool_id,
        name="test external Skill",
        description="Validate parameters of external Skill schema",
        category=ToolCategory.EXTERNAL,
        source="generated",
        parameters=[
            ToolParameter(name="symbol", type="string", description="Stock code", required=True),
            ToolParameter(name="periods", type="integer", description="Period", required=False, default=8),
        ],
    )

    registry.register(metadata, override=True)
    registry.register_function(
        tool_id=tool_id,
        func=external_skill_wrapper,
        name="test external Skill",
        category="external",
        description="Validate parameters of external Skill schema",
        override=True,
        parameters=metadata.parameters,
    )
    registry._tools[tool_id].source = "generated"

    try:
        tool = registry.get_langchain_tool(tool_id)

        assert tool is not None
        result = tool.invoke({"symbol": "002594"})

        assert result == "symbol=002594,periods=8"
        assert tool.args_schema is not None
        schema_fields = tool.args_schema.model_fields
        assert "symbol" in schema_fields
        assert "periods" in schema_fields
    finally:
        registry.unregister(tool_id)

# === Merged from test_fundamental_factors_gross_margin.py ===
"""Fundamental Factor Gross Margin Field Priority Test."""

from core.skill_runtime import fundamental_factors


def test_estimate_gross_margin_prefers_grossprofit_margin_over_raw_gross_margin() -> None:
    record = {
        "financial_indicators": {
            "gross_margin": 139609610.88,
            "grossprofit_margin": 26.8,
        }
    }

    assert fundamental_factors._estimate_gross_margin(record) == 26.8

# === Merged from test_latest_price_consistency.py ===

from unittest.mock import AsyncMock

import pytest

from app.routers import stock_sync
from core.skill_runtime import data_access


def test_get_latest_stock_price_prefers_close_when_current_price_is_stale(monkeypatch) -> None:
    monkeypatch.setattr(
        data_access,
        "get_market_quotes",
        lambda symbol: {
            "symbol": symbol,
            "close": 1459.44,
            "current_price": 1399.0,
            "pre_close": 1450.0,
        },
        raising=True,
    )
    monkeypatch.setattr(data_access, "get_stock_basic_info", lambda symbol: None, raising=True)

    assert data_access.get_latest_stock_price("600519") == 1459.44


@pytest.mark.asyncio
async def test_sync_latest_to_market_quotes_aligns_price_fields(monkeypatch) -> None:
    latest_doc = {
        "symbol": "600519",
        "close": 1459.44,
        "open": 1464.49,
        "high": 1469.99,
        "low": 1452.88,
        "volume": 123456,
        "amount": 78901234,
        "pct_chg": 0.65,
        "pre_close": 1450.0,
        "trade_date": "2025-11-05",
    }
    existing_quote = {
        "code": "600519",
        "trade_date": "2025-11-04",
        "current_price": 1399.0,
    }

    stock_daily_quotes = type("StockDailyQuotesCollection", (), {
        "find_one": AsyncMock(return_value=latest_doc),
    })()
    market_quotes = type("MarketQuotesCollection", (), {
        "find_one": AsyncMock(return_value=existing_quote),
        "update_one": AsyncMock(),
    })()
    fake_db = type("FakeDb", (), {
        "stock_daily_quotes": stock_daily_quotes,
        "market_quotes": market_quotes,
    })()

    monkeypatch.setattr(stock_sync, "get_mongo_db", lambda: fake_db, raising=True)

    await stock_sync._sync_latest_to_market_quotes("600519")

    market_quotes.update_one.assert_awaited_once()
    _, update_doc = market_quotes.update_one.await_args.args[:2]
    quote_data = update_doc["$set"]
    assert quote_data["close"] == 1459.44
    assert quote_data["price"] == 1459.44
    assert quote_data["current_price"] == 1459.44

# === Merged from test_legacy_dependency_provider_memory.py ===
from core.workflow import builder as builder_module
from tradingagents.core.engine import memory_provider as memory_provider_module


class _FakeMemoryProvider:
    def __init__(self, config=None, memory_enabled=True):
        self.config = config or {}
        self.memory_enabled = memory_enabled
        self.requested = []

    def get_memory(self, memory_type):
        self.requested.append(memory_type)
        return {"memory_type": memory_type}


def test_legacy_dependency_provider_uses_memory_provider(monkeypatch):
    fake_provider = _FakeMemoryProvider()

    builder_module.LegacyDependencyProvider.reset_instance()
    monkeypatch.setattr(memory_provider_module, "MemoryProvider", lambda config=None, memory_enabled=True: fake_provider)

    provider = builder_module.LegacyDependencyProvider({"memory_enabled": True})

    provider._create_memory("bull_memory")

    assert fake_provider.requested == ["bull_memory"]
    assert provider.get_memory("bull_memory") == {"memory_type": "bull_memory"}


def test_legacy_dependency_provider_resets_memory_cache_on_config_update():
    builder_module.LegacyDependencyProvider.reset_instance()

    provider = builder_module.LegacyDependencyProvider.get_instance({"memory_enabled": True})
    provider._memories["bull_memory"] = {"memory_type": "bull_memory"}
    provider._memory_provider = object()

    refreshed = builder_module.LegacyDependencyProvider.get_instance({"memory_use_mem0_compat": True})

    assert refreshed is provider
    assert refreshed._memories == {}
    assert refreshed._memory_provider is None

# === Merged from test_logging_config.py ===
import os
from importlib import reload
from pathlib import Path

import pytest


MINIMAL_TOML = """
[logging]
level = "INFO"

[logging.format]
console = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
file = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

[logging.handlers.file]
directory = "./logs"
level = "DEBUG"
max_size = "1MB"
backup_count = 1
"""


@pytest.mark.parametrize("profile, expect_name", [
    ("", "logging.toml"),
    ("docker", "logging_docker.toml"),
])
def test_logging_uses_expected_toml(profile, expect_name, monkeypatch, tmp_path, caplog):
    # Arrange: create temporary config directory with desired files
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # default config
    (cfg_dir / "logging.toml").write_text(MINIMAL_TOML, encoding="utf-8")
    # docker config (only when needed)
    (cfg_dir / "logging_docker.toml").write_text(MINIMAL_TOML, encoding="utf-8")

    # Switch CWD to the temp project root
    monkeypatch.chdir(tmp_path)

    # Clear/set env
    if profile:
        monkeypatch.setenv("LOGGING_PROFILE", profile)
    else:
        monkeypatch.delenv("LOGGING_PROFILE", raising=False)
        monkeypatch.delenv("DOCKER", raising=False)

    # Import after chdir to ensure relative paths resolve under tmp_path
    from app.core import logging_config as lc
    reload(lc)

    # Act: resolve which file will be used, then apply logging
    chosen = lc.resolve_logging_cfg_path()
    assert chosen.name == expect_name
    lc.setup_logging("INFO")


# === Merged from test_logging_json.py ===
from importlib import reload
import logging


def test_json_console_formatter_enabled(monkeypatch, tmp_path):
    # Arrange: TOML with json flag
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "logging.toml").write_text(
        """
[logging]
level = "INFO"

[logging.format]
json = true
        """.strip(),
        encoding="utf-8",
    )

    # Set CWD to temp
    monkeypatch.chdir(tmp_path)

    # Import module fresh
    from app.core import logging_config as lc
    reload(lc)

    # Act
    lc.setup_logging("INFO")

    # Assert: console handler uses SimpleJsonFormatter
    logger = logging.getLogger("webapi")
    # find console handler
    console_handlers = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
    assert console_handlers, "no console handler found"
    formatter_names = {h.formatter.__class__.__name__ for h in console_handlers if h.formatter}
    assert "SimpleJsonFormatter" in formatter_names


# === Merged from test_pipeline_timeout_controls.py ===
# -*- coding: utf-8 -*-
"""Pipeline timeout control and Judge model hierarchical testing.

Background: Code generation using the deep thinking model often takes 3-6 minutes, and the default timeout is 240s and is triggered multiple times.
"Request timed out", And the OpenAI SDK timed out message (timed out) and retry keyword
 (timeout) Mismatch results in never retrying; Judge quality assessment is a judgment task but is bound
Think about models. This group of tests covers: retry after timeout, Judge s fast model, code generation
Timeout can be overridden on a per-time basis.
"""
from types import SimpleNamespace

from core.tools.external.code_generator import (
    CODEGEN_LLM_TIMEOUT_SECONDS,
    CodeGenerator,
)
from core.tools.external.output_evaluator import OutputEvaluator
from core.utils.retry import is_retryable


class _FakeClient:
    def __init__(self, content: str = "ok", raise_exc: Exception | None = None):
        self._content = content
        self._raise = raise_exc
        self.calls = 0

    def chat(self, messages, **kwargs):
        self.calls += 1
        if self._raise:
            raise self._raise
        return SimpleNamespace(content=self._content)


# ---------- Retry after timeout ----------

def test_openai_timeout_message_is_retryable():
    # OpenAI SDK The timeout message is "Request timed out." (timed out two words),
    # Previously, the keyword list only had "timeout" As a result, the match cannot be matched and never retried.
    assert is_retryable(Exception("Request timed out.")) is True
    assert is_retryable(Exception("APITimeoutError: Request timed out.")) is True
    assert is_retryable(Exception("Read timeout")) is True


def test_non_retryable_error_still_not_retried():
    assert is_retryable(Exception("Error code: 403 - AccountOverdueError")) is False
    assert is_retryable(ValueError("bad spec")) is False


# ---------- Judge Go fast model ----------

def test_judge_uses_quick_model():
    quick, main = _FakeClient("<verdict>{}</verdict>"), _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main, quick_llm_client=quick)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert quick.calls == 1
    assert main.calls == 0


def test_judge_falls_back_to_main():
    quick = _FakeClient(raise_exc=RuntimeError("Error code: 403"))
    main = _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main, quick_llm_client=quick)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert main.calls == 1


def test_judge_without_quick_uses_main():
    main = _FakeClient("<verdict>{}</verdict>")
    evaluator = OutputEvaluator(llm_client=main)

    out = evaluator._call_judge_llm_simple("Evaluation output", "tid")

    assert out == "<verdict>{}</verdict>"
    assert main.calls == 1


# ---------- Code generation timeout pay-per-view coverage ----------

class _FakeAdapterClient:
    """Fake client with adapter/config structure for authentication timeout override"""

    def __init__(self, timeout: int):
        self._adapter = SimpleNamespace(
            config=SimpleNamespace(timeout=timeout),
            initialize=lambda: None,
        )


def test_codegen_default_timeout_is_480():
    assert CODEGEN_LLM_TIMEOUT_SECONDS == 480


def test_codegen_get_client_overrides_timeout():
    client = _FakeAdapterClient(timeout=240)
    generator = CodeGenerator(llm_client=client)  # type: ignore[arg-type]

    generator._get_client(timeout_seconds=900)

    assert client._adapter.config.timeout == 900


def test_codegen_get_client_resets_to_smaller_timeout():
    # Users can adjust the timeout smaller (for example, after switching to a fast model). It cannot just increase the timeout but not decrease it.
    client = _FakeAdapterClient(timeout=900)
    generator = CodeGenerator(llm_client=client)  # type: ignore[arg-type]

    generator._get_client(timeout_seconds=120)

    assert client._adapter.config.timeout == 120

# === Merged from test_researcher_memory.py ===
from typing import Any, Dict

from core.agents.researcher import ResearcherAgent


class _TestResearcherAgent(ResearcherAgent):
    researcher_type = "test"
    output_field = "test_report"
    stance = "bull"
    debate_state_field = "investment_debate_state"
    history_field = "bull_history"
    opponent_history_field = "bear_history"

    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        return "system"

    def _build_user_prompt(self, ticker: str, analysis_date: str, reports: Dict[str, Any], historical_context: str, state: Dict[str, Any]) -> str:
        return historical_context or "user"

    def _get_required_reports(self):
        return ["market_report"]


class _Mem0StyleMemory:
    def __init__(self):
        self.search_calls = []
        self.add_calls = []

    def search_memories(self, query, n_results=5, filter_metadata=None):
        self.search_calls.append({"query": query, "n_results": n_results, "filter_metadata": filter_metadata})
        return [{"content": "Historical research experience A", "similarity": 0.95, "metadata": {"ticker": "300750"}}]

    def add_memory(self, content, metadata=None, memory_id=None):
        self.add_calls.append({"content": content, "metadata": metadata, "memory_id": memory_id})
        return True


class _LegacyStyleMemory:
    pass


def test_researcher_agent_reads_history_from_mem0_style_memory():
    memory = _Mem0StyleMemory()
    agent = _TestResearcherAgent(memory=memory)

    context = agent._get_memory_context("300750", {"market_report": "current report"})

    assert " [Historical experience]" in context
    assert "Historical research experience A" in context
    assert memory.search_calls


def test_researcher_agent_skips_history_when_memory_lacks_search_interface():
    agent = _TestResearcherAgent(memory=_LegacyStyleMemory())

    context = agent._get_memory_context("300750", {"market_report": "current report"})

    assert context == ""


def test_researcher_agent_saves_to_mem0_style_memory():
    memory = _Mem0StyleMemory()
    agent = _TestResearcherAgent(memory=memory)

    agent._save_to_memory("300750", {"content": "new research report"})

    assert len(memory.add_calls) == 1
    assert memory.add_calls[0]["metadata"]["ticker"] == "300750"
    assert memory.add_calls[0]["metadata"]["stance"] == "bull"


def test_researcher_agent_skips_save_when_memory_lacks_add_interface():
    agent = _TestResearcherAgent(memory=_LegacyStyleMemory())

    agent._save_to_memory("300750", {"content": "new research report"})

# === Merged from test_seed_project_memory_defaults.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "seed_project_memory_defaults.py"

spec = importlib.util.spec_from_file_location("seed_project_memory_defaults", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


class _FakeUpdateResult:
    def __init__(self, matched_count: int = 1):
        self.matched_count = matched_count


class _FakeCursor:
    def __init__(self, docs):
        self._docs = [dict(doc) for doc in docs]

    def sort(self, sort_spec):
        for field, direction in reversed(sort_spec):
            reverse = direction < 0
            self._docs.sort(key=lambda doc: doc.get(field), reverse=reverse)
        return self

    def limit(self, size):
        self._docs = self._docs[:size]
        return self

    async def to_list(self, length):
        return [dict(doc) for doc in self._docs[:length]]


class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def update_one(self, query, update, upsert=False):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                doc.update(update.get("$set", {}))
                return _FakeUpdateResult()
        if upsert:
            new_doc = dict(query)
            new_doc.update(update.get("$setOnInsert", {}))
            new_doc.update(update.get("$set", {}))
            self.docs.append(new_doc)
        return _FakeUpdateResult()

    async def find_one(self, query):
        for doc in self.docs:
            if all(doc.get(key) == value for key, value in query.items()):
                return dict(doc)
        return None

    def find(self, query):
        matched = []
        for doc in self.docs:
            ok = True
            for key, value in query.items():
                if isinstance(value, dict) and "$in" in value:
                    if doc.get(key) not in value["$in"]:
                        ok = False
                        break
                elif doc.get(key) != value:
                    ok = False
                    break
            if ok:
                matched.append(doc)
        return _FakeCursor(matched)


class _FakeDB:
    def __init__(self):
        self._collection = _FakeCollection()

    def __getitem__(self, name):
        assert name == "project_memory_items"
        return self._collection


def test_seed_project_memory_defaults_script_passes(monkeypatch):
    monkeypatch.setattr(module, "get_mongo_db", lambda: _FakeDB())

    summary = asyncio.run(module.seed_defaults())

    assert summary["ok"] is True
    assert summary["count"] >= 6
    assert "global-no-trading-advice" in summary["memory_keys"]
    assert "stock-analysis-template" in summary["memory_keys"]

# === Merged from test_settings.py ===
from app.core.config import Settings


def test_settings_defaults_and_env_override(monkeypatch):
    # Override a few env vars
    monkeypatch.setenv("PORT", "8123")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("MONGODB_USERNAME", "user")
    monkeypatch.setenv("MONGODB_PASSWORD", "pass")
    monkeypatch.setenv("MONGODB_HOST", "dbhost")
    monkeypatch.setenv("MONGODB_PORT", "27018")
    monkeypatch.setenv("MONGODB_DATABASE", "testdb")
    monkeypatch.setenv("MONGODB_AUTH_SOURCE", "admin")

    s = Settings()  # instantiate fresh to pick up env

    assert s.PORT == 8123
    assert s.DEBUG is False

    # URI should include credentials when provided
    uri = s.MONGO_URI
    assert uri.startswith("mongodb://user:pass@dbhost:27018/")
    assert uri.endswith("testdb?authSource=admin")


def test_redis_url_builds(monkeypatch):
    # Without password
    monkeypatch.setenv("REDIS_HOST", "127.0.0.1")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_DB", "2")
    # Ensure no password from .env leaks into this test
    monkeypatch.setenv("REDIS_PASSWORD", "")

    s = Settings()
    assert s.REDIS_URL == "redis://127.0.0.1:6379/2"

    # With password
    monkeypatch.setenv("REDIS_PASSWORD", "p@ss")
    s = Settings()
    assert s.REDIS_URL == "redis://:p@ss@127.0.0.1:6379/2"


# === Merged from test_stocks_kline_news_api.py ===
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from unittest.mock import patch

# Build a minimal app that mounts only the stocks router to avoid triggering app.main lifespan
from app.routers import stocks as stocks_router
from app.routers.auth import get_current_user


def create_test_app():
    app = FastAPI()
    app.include_router(stocks_router.router, prefix="/api")
    # Override auth dependency to bypass Bearer token in tests
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "test",
        "username": "test",
        "is_admin": True,
        "roles": ["admin"],
    }
    return app


@pytest.fixture()
def client():
    app = create_test_app()
    with TestClient(app) as c:
        yield c


def test_kline_ok_source_and_adj(client):
    # Mock DataSourceManager fallback to return 2 bars
    items = [
        {"time": "2024-09-01", "open": 10.0, "high": 10.5, "low": 9.8, "close": 10.2, "volume": 100000.0, "amount": 2.3e6},
        {"time": "2024-09-02", "open": 10.2, "high": 10.8, "low": 10.0, "close": 10.6, "volume": 120000.0, "amount": 2.8e6},
    ]
    with patch("app.services.data_sources.manager.DataSourceManager.get_kline_with_fallback", return_value=(items, "tushare")):
        resp = client.get("/api/stocks/000001/kline", params={"period": "day", "limit": 2, "adj": "qfq"})
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body.get("data")
        assert data["code"] == "000001"
        assert data["period"] == "day"
        assert data["limit"] == 2
        assert data["adj"] == "qfq"
        assert data["source"] == "tushare"
        assert isinstance(data["items"], list) and len(data["items"]) == 2


def test_kline_invalid_period_returns_400(client):
    resp = client.get("/api/stocks/000001/kline", params={"period": "2m", "limit": 10})
    assert resp.status_code == 400
    j = resp.json()
    # FastAPI default error format
    assert j["detail"].startswith("Not supported period")


def test_news_ok_with_announcements_and_source(client):
    items = [
        {"title": "Announcement sample", "source": "tushare", "time": "2024-09-02", "url": "http://x", "type": "announcement"},
        {"title": "news sample", "source": "tushare", "time": "2024-09-02 10:00:00", "url": "http://y", "type": "news"},
    ]
    with patch("app.services.data_sources.manager.DataSourceManager.get_news_with_fallback", return_value=(items, "tushare")):
        resp = client.get("/api/stocks/000001/news", params={"days": 2, "limit": 2, "include_announcements": True})
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("success") is True
        data = body.get("data")
        assert data["code"] == "000001"
        assert data["days"] == 2
        assert data["limit"] == 2
        assert data["include_announcements"] is True
        assert data["source"] == "tushare"
        assert isinstance(data["items"], list) and len(data["items"]) == 2


# === Merged from test_tool_normalizer.py ===
from core.llm.models import ToolCall
from core.llm.tool_normalizer import ToolCallNormalizer


def test_execute_tool_call_unwraps_nested_kwargs_payload():
    received = {}

    def analyze_a_share_dupont(symbol: str, periods: int = 8):
        received["symbol"] = symbol
        received["periods"] = periods
        return {"symbol": symbol, "periods": periods}

    tool_call = ToolCall(
        id="call-1",
        name="analyze_a_share_dupont",
        arguments={
            "kwargs": {
                "symbol": "600519.SH",
                "periods": 4,
            }
        },
    )

    result = ToolCallNormalizer.execute_tool_call(
        tool_call,
        {"analyze_a_share_dupont": analyze_a_share_dupont},
    )

    assert result.is_error is False
    assert received == {"symbol": "600519", "periods": 4}
    assert '"symbol": "600519"' in result.content


def test_execute_tool_call_prefers_explicit_context_over_nested_kwargs():
    received = {}

    def analyze_a_share_dupont(symbol: str, periods: int = 8, request_id: str | None = None):
        received["symbol"] = symbol
        received["periods"] = periods
        received["request_id"] = request_id
        return "ok"

    tool_call = ToolCall(
        id="call-2",
        name="analyze_a_share_dupont",
        arguments={
            "kwargs": {
                "symbol": "600519",
                "periods": 2,
                "request_id": "old",
            }
        },
    )

    result = ToolCallNormalizer.execute_tool_call(
        tool_call,
        {"analyze_a_share_dupont": analyze_a_share_dupont},
        request_id="new",
    )

    assert result.is_error is False
    assert received == {"symbol": "600519", "periods": 2, "request_id": "new"}

# === Merged from test_trader_memory.py ===
from typing import Any, Dict, List, Optional

from core.agents.trader import TraderAgent


class _TestTraderAgent(TraderAgent):
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        return "system"

    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        investment_plan: Dict[str, Any],
        all_reports: Dict[str, Any],
        historical_trades: Optional[List[Dict[str, Any]]],
        state: Dict[str, Any],
    ) -> str:
        return "user"


class _Mem0StyleMemory:
    def __init__(self):
        self.search_calls = []
        self.add_calls = []

    def search_memories(self, query, n_results=5, filter_metadata=None):
        self.search_calls.append(
            {"query": query, "n_results": n_results, "filter_metadata": filter_metadata}
        )
        return [
            {
                "content": "Historical trading plan A",
                "metadata": {"ticker": "300750", "source": "mem0"},
                "similarity": 0.93,
            }
        ]

    def add_memory(self, content, metadata=None, memory_id=None):
        self.add_calls.append({"content": content, "metadata": metadata, "memory_id": memory_id})
        return True


class _LegacyStyleMemory:
    def __init__(self):
        self.get_calls = []
        self.add_calls = []

    def get_memories(self, current_situation, n_matches=1):
        self.get_calls.append({"current_situation": current_situation, "n_matches": n_matches})
        return [
            {
                "situation": "Stock code: 300750\n Transaction Analysis Plan",
                "recommendation": "Historical trading plan B",
                "similarity": 0.81,
            }
        ]

    def add_situations(self, situations_and_advice):
        self.add_calls.append(list(situations_and_advice))


def test_trader_agent_get_historical_trades_from_mem0_style_memory():
    memory = _Mem0StyleMemory()
    agent = _TestTraderAgent(memory=memory)

    memories = agent._get_historical_trades("300750")

    assert memories == [
        {
            "content": "Historical trading plan A",
            "metadata": {"ticker": "300750", "source": "mem0"},
            "similarity": 0.93,
        }
    ]
    assert memory.search_calls == [
        {
            "query": "Stock code: 300750\n Transaction Analysis Plan\n Historical trading experience",
            "n_results": 3,
            "filter_metadata": {"ticker": "300750"},
        }
    ]


def test_trader_agent_returns_none_when_memory_lacks_search_interface():
    memory = _LegacyStyleMemory()
    agent = _TestTraderAgent(memory=memory)

    memories = agent._get_historical_trades("300750")

    assert memories is None
    assert memory.get_calls == []


def test_trader_agent_save_to_mem0_style_memory():
    memory = _Mem0StyleMemory()
    agent = _TestTraderAgent(memory=memory)

    agent._save_to_memory("300750", {"content": "New Transaction Analysis Program", "market_view": "bullish"})

    assert len(memory.add_calls) == 1
    call = memory.add_calls[0]
    assert call["content"] == "{\"content\": \"New Transaction Analysis Program\", \"market_view\": \"bullish\"}"
    assert call["metadata"]["ticker"] == "300750"
    assert call["metadata"]["agent_id"] == agent.agent_id
    assert call["metadata"]["memory_kind"] == "trader_plan"
    assert call["metadata"]["output_field"] == agent.output_field


def test_trader_agent_skips_save_when_memory_lacks_add_interface():
    memory = _LegacyStyleMemory()
    agent = _TestTraderAgent(memory=memory)

    agent._save_to_memory("300750", {"content": "New Transaction Analysis Program", "market_view": "bullish"})

    assert memory.add_calls == []

# === Merged from test_validate_agent_workshop_l6_forward_consumption_loop.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_agent_workshop_l6_forward_consumption_loop.py"

spec = importlib.util.spec_from_file_location("validate_agent_workshop_l6_forward_consumption_loop", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_validate_agent_workshop_l6_forward_consumption_loop_passes():
    summary = asyncio.run(module.validate_all())

    assert summary["ok"] is True
    assert summary["checks"] == {
        "requirement_lessons_injected": True,
        "gap_analysis_lessons_injected": True,
        "build_version_lessons_injected": True,
        "build_version_constraints_include_lesson_fix": True,
        "three_stage_recall_calls": True,
        "all_recall_scoped_by_spec": True,
        "all_recall_use_same_user": True,
        "three_stage_observation_logs": True,
        "all_observation_stages_present": True,
        "all_observations_hit": True,
        "all_observations_scoped_by_spec": True,
        "all_observations_use_same_user": True,
        "build_version_completed": True,
    }

# === Merged from test_validate_agent_workshop_production_review_project_memory_loop.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_agent_workshop_production_review_project_memory_loop.py"

spec = importlib.util.spec_from_file_location("validate_agent_workshop_production_review_project_memory_loop", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_validate_agent_workshop_production_review_project_memory_loop_passes():
    summary = asyncio.run(module.validate_all())

    assert summary["ok"] is True
    assert summary["checks"] == {
        "runtime_prompt_accepts_current_l4": True,
        "runtime_prompt_missing_l4_revises_review": True,
        "runtime_prompt_missing_l4_records_issue": True,
        "missing_system_prompt_marks_evidence_incomplete": True,
        "missing_system_prompt_records_invalid_reason": True,
    }

# === Merged from test_validate_agent_workshop_prompt_template_project_memory_loop.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_agent_workshop_prompt_template_project_memory_loop.py"

spec = importlib.util.spec_from_file_location("validate_agent_workshop_prompt_template_project_memory_loop", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_validate_agent_workshop_prompt_template_project_memory_loop_passes():
    summary = asyncio.run(module.validate_all())

    assert summary["ok"] is True
    assert summary["checks"] == {
        "template_created": True,
        "system_prompt_contains_l4": True,
        "system_prompt_contains_rule": True,
        "constraints_contains_l4_guard": True,
        "constraints_contains_output_constraint": True,
    }

# === Merged from test_validate_manager_memory_runtime.py ===
import sys
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


MODULE_PATH = ROOT_DIR / "scripts" / "validate_manager_memory_runtime.py"
SPEC = importlib.util.spec_from_file_location("validate_manager_memory_runtime", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_configure_runtime_mode = MODULE._configure_runtime_mode


def test_configure_runtime_mode_uses_mem0_only(monkeypatch):
    monkeypatch.delenv("MEM0_FORCE_PRIMARY", raising=False)
    monkeypatch.delenv("MEMORY_USE_MEM0_COMPAT", raising=False)

    updates = _configure_runtime_mode("mem0-only", "validation_user_1")

    assert updates == {
        "MEM0_COMPAT_USER_ID": "validation_user_1",
        "MEMORY_USE_MEM0_COMPAT": "true",
        "MEM0_FORCE_PRIMARY": "true",
    }

# === Merged from test_validate_mem0_cutover_routing.py ===
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_mem0_cutover_routing.py"

spec = importlib.util.spec_from_file_location("validate_mem0_cutover_routing", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_workflow_builder_smoke_respects_mem0_only(monkeypatch):
    monkeypatch.delenv("MEM0_FORCE_PRIMARY", raising=False)
    monkeypatch.delenv("MEMORY_USE_MEM0_COMPAT", raising=False)

    updates = module._configure_runtime_mode("mem0-only", "cutover_test_user")
    result = module._run_workflow_builder_smoke()

    assert updates["MEM0_FORCE_PRIMARY"] == "true"
    assert result["requested_agent_ids"] == ["research_manager_v2"]
    assert result["memory_payload"]["agent_id"] == "research_manager_v2"
    assert result["memory_payload"]["force_primary_env"] == "true"


def test_trading_graph_smoke_respects_mem0_only(monkeypatch):
    monkeypatch.delenv("MEM0_FORCE_PRIMARY", raising=False)
    monkeypatch.delenv("MEMORY_USE_MEM0_COMPAT", raising=False)

    updates = module._configure_runtime_mode("mem0-only", "cutover_test_user_graph")
    result = module._run_trading_graph_smoke()

    assert updates["MEM0_FORCE_PRIMARY"] == "true"
    assert result["requested_memory_names"] == [
        "bull_memory",
        "bear_memory",
        "trader_memory",
        "invest_judge_memory",
        "risk_manager_memory",
    ]
    assert result["provider_memory_use_mem0_compat"] is True
    assert result["force_primary_env"] == "true"

# === Merged from test_validate_memory_consumption_loops.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_memory_consumption_loops.py"

spec = importlib.util.spec_from_file_location("validate_memory_consumption_loops", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_assistant_memory_block_reaches_prompt():
    result = asyncio.run(module._run_assistant_consumption_smoke())

    assert result["memory_block"].startswith(" [Historical preferences]")
    assert result["prompt_contains_memory"] is True
    assert result["prompt_contains_topic"] is True


def test_analysis_memory_block_reaches_workflow_inputs():
    result = asyncio.run(module._run_analysis_consumption_smoke())

    assert result["injected_growth_memory"] is True
    assert result["injected_mem0_memory"] is True
    assert " [Growth memory]" in result["combined_block"]
    assert " [Historical analysis]" in result["combined_block"]


def test_growth_approved_memory_reaches_recall_context():
    result = asyncio.run(module._run_growth_approval_consumption_smoke())

    assert result["approved"] is True
    assert result["bridged_to_mem0"] is True
    assert result["bridge_scope"] == "agent_experience"
    assert result["context_contains_header"] is True
    assert result["context_contains_title"] is True
    assert result["context_contains_summary"] is True


def test_skill_lessons_reach_initial_feedback():
    result = asyncio.run(module._run_skill_consumption_smoke())

    assert result["feedback_contains_mem0_lessons"] is True
    assert result["feedback_contains_original_feedback"] is True
    assert " [Historical Lessons]" in result["final_initial_feedback"]
    assert " [User feedback]" in result["final_initial_feedback"]


def test_validate_all_passes():
    summary = asyncio.run(module.validate_all())

    assert summary["ok"] is True
    assert summary["checks"] == {
        "assistant_prompt_injection": True,
        "analysis_input_injection": True,
        "growth_approved_memory_consumption": True,
        "skill_feedback_injection": True,
    }

# === Merged from test_validate_project_memory_l4_loop.py ===
import asyncio
import importlib.util
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT_DIR / "scripts" / "validate_project_memory_l4_loop.py"

spec = importlib.util.spec_from_file_location("validate_project_memory_l4_loop", SCRIPT_PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(module)


def test_validate_project_memory_l4_loop_passes():
    summary = asyncio.run(module.validate_all())

    assert summary["ok"] is True
    assert summary["checks"] == {
        "l4_write_success": True,
        "l4_read_success": True,
        "l4_prompt_block_built": True,
        "assistant_injection_contains_l4": True,
        "assistant_injection_keeps_l5_l6": True,
    }
