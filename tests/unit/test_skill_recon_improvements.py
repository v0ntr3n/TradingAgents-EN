# -*- coding: utf-8 -*-
"""Skill Single test of three improvements in the generator reconnaissance layer.

Background (dongchedi model sales case review): The requirement specifies data sources outside the catalog"Understand car emperor", 
Reconnaissance level——
① Consider the 7 vector recalls of unrelated stock instruments as"The data source has been covered by the helper"; 
② Silently fallback sources outside the directory as recommended by AKShare/Tushare;
③ The specification invents acceptance fields such as model_id/manufacturer_id that do not exist in the interface and no warning is issued.

This test focuses on three improvement points:
1. Requirement type diversion (external_api vs local_data);
2. Data sources outside the directory are explicitly marked (unknown_data_source), and fallback is no longer used to make up the number;
3. Consistency verification between acceptance fields and hit asset capabilities (low coverage reduces confidence + clarification prompt).
"""
from types import SimpleNamespace

from core.tools.external.external_data_source_catalog import is_known_external_source
from core.tools.external.reconnaissance_controller import DefaultReconnaissanceController
from core.tools.external.requirement_analyzer import RequirementAnalyzer
from core.tools.external.skill_spec import (
    ExpectedOutput,
    ImplementationFactReport,
    SkillParameter,
    SkillSpec,
)


def _controller() -> DefaultReconnaissanceController:
    return DefaultReconnaissanceController()


def _dongchedi_spec() -> SkillSpec:
    """Replicate the accident scene: Specify vehicle model sales requirements from data sources outside the catalog."""
    return SkillSpec(
        tool_id="dongchedi_manufacturer_monthly_model_sales",
        display_name="Understand the monthly sales inquiry of car manufacturers models",
        description=(
            "Based on the HTTP interface of the national car sales list published by Dianchedi, it supports specifying the statistical dimensions of a single month, the past six months, and the past year."
            "Through paged pulling and manufacturer filtering logic, data such as sales volume and national rankings of corresponding models of all car series under the specified manufacturer are obtained;"
            "The interface does not require identity authentication and only needs to construct legal request headers to access."
        ),
        category="market",
        data_source="dongchedi",
        parameters=[
            SkillParameter(name="manufacturer", type="string", description="The name of the target manufacturer or the manufacturer who understands the Chedi platform ID"),
            SkillParameter(name="month_dim", type="string", description="statistical dimension YYYYMM / 500 / 1000"),
        ],
        expected_output=ExpectedOutput(
            type="list[dict]",
            fields=["month_dim", "rank", "series_id", "series_name", "sales_volume", "data_source"],
        ),
    )


def _news_spec() -> SkillSpec:
    """Known data sources + Native data class requirements (return to baseline, behavior should not change)."""
    return SkillSpec(
        tool_id="get_eastmoney_news",
        display_name="Oriental Fortune Stock News",
        description="Query the Oriental Fortune stock news list and return the title, link, and release time",
        category="news",
        data_source="akshare",
        expected_output=ExpectedOutput(
            type="list[dict]",
            fields=["title", "url", "publish_time"],
        ),
    )


class TestIsKnownExternalSource:
    """Directory source determination (common basis for improvement point 1/2)."""

    def test_known_sources(self):
        for name in ("akshare", "AKShare", "tushare", "Oriental Fortune", "eastmoney", "finnhub", "google news"):
            assert is_known_external_source(name) is True, name

    def test_unknown_sources(self):
        for name in ("dongchedi", "Understand car emperor", "amap", ""):
            assert is_known_external_source(name) is False, name


class TestRequirementModeClassification:
    """Improvement point 1: Requirement type diversion."""

    def test_unknown_data_source_routes_to_external_api(self):
        assert _controller()._classify_requirement_mode(_dongchedi_spec()) == "external_api"

    def test_url_in_description_routes_to_external_api(self):
        spec = SkillSpec(
            tool_id="t_x", display_name="t", category="utility",
            description="call https://api.example.com/v1/data Interface to get data",
        )
        assert _controller()._classify_requirement_mode(spec) == "external_api"

    def test_public_api_keyword_routes_to_external_api(self):
        spec = SkillSpec(
            tool_id="t_x", display_name="t", category="utility",
            description="Obtain car sales data through public interface",
        )
        assert _controller()._classify_requirement_mode(spec) == "external_api"

    def test_known_source_stays_local(self):
        assert _controller()._classify_requirement_mode(_news_spec()) == "local_data"

    def test_plain_stock_spec_stays_local(self):
        spec = SkillSpec(
            tool_id="get_pledge_risk", display_name="Equity pledge risk",
            description="Query the risk profile of individual stock equity pledges", category="fundamentals",
        )
        assert _controller()._classify_requirement_mode(spec) == "local_data"


class TestBuildRecommendationsUnknownSource:
    """Improvement point 2: Explicitly label data sources outside the directory without fallback."""

    def test_unknown_source_returns_empty_and_flag(self):
        rec = RequirementAnalyzer().build_recommendations(spec=_dongchedi_spec())
        assert rec["unknown_data_source"] == "dongchedi"
        assert rec["stock_collections"] == []
        assert rec["external_sources"] == []
        # Sent to the front end in demand mode: external_api mode does not display local/directory assets
        assert rec["requirement_mode"] == "external_api"

    def test_known_source_keeps_recommendations(self):
        rec = RequirementAnalyzer().build_recommendations(spec=_news_spec())
        assert rec["unknown_data_source"] == ""
        assert "akshare" in rec["external_sources"]
        assert rec["requirement_mode"] == "local_data"


class TestExternalApiModeRecon:
    """Improvement points 1+2+3 End-to-end effects on the rules reconnaissance main process."""

    def test_dongchedi_flow(self):
        # Pseudo-vector recall (an irrelevant stock tool that simulates accident scenes)
        fake_hits = [
            SimpleNamespace(
                capability={"source_type": "builtin_tool", "bindable": True,
                            "registry_tool_id": f"tool_{i}", "name": f"tool_{i}",
                            "description": "stock instruments"},
                score=0.42,
            )
            for i in range(3)
        ]
        report = _controller()._rule_based_analyze(_dongchedi_spec(), capability_hits=fake_hits)

        # Improvement point 1: The strategy is switched to external API integration; local tools for vector recall are not adopted
        assert "External HTTP API integration" in report.recommended_strategy
        assert "dongchedi" in report.recommended_strategy
        assert report.available_helpers == []
        assert any("Not adopted" in f.fact for f in report.schema_facts)

        # Improvement point 2: Sources outside the directory explicitly register runtime gaps and comments instead of silently fallback
        assert any(g.path == "external_data_source:dongchedi" for g in report.runtime_gaps)
        assert any("Not in the external data source directory known to the system" in n for n in report.notes)
        # Recommended collections/external sources no longer appear to round up stock assets
        assert not any("market_quotes" in f.fact for f in report.schema_facts)

        # Improvement point 3: Acceptance field prompts"The actual response of the interface shall prevail."
        assert any("The actual response from the external interface shall prevail." in n for n in report.notes)

        # The confidence level is no longer falsely high due to local collection samples (the local collection has been cleared)
        assert report.confidence <= 0.45

    def test_local_mode_behavior_unchanged(self, monkeypatch):
        """Return: Known Source + The scouting behavior required by local data classes remains unchanged."""
        import core.skill_runtime.project_access as pa

        monkeypatch.setattr(
            pa, "inspect_stock_collection_schema",
            lambda *a, **k: {"sample_count": 3, "top_level_fields": ["title", "url", "publish_time"]},
        )
        report = _controller()._rule_based_analyze(_news_spec(), capability_hits=None)
        assert report.recommended_strategy.startswith("priority use skill_runtime")
        # Collection sample fields are injected as usual (for field coverage pooling)
        assert report.sample_fields.get("stock_news") == ["title", "url", "publish_time"]
        # All acceptance fields can be produced by collections → No coverage alarm
        assert not any("Insufficient coverage of acceptance fields" in n for n in report.notes)


class TestFieldCoverageValidation:
    """Improvement point 3: Unit behavior of acceptance field consistency check."""

    def _spec_with_fields(self, fields):
        return SkillSpec(
            tool_id="t_c", display_name="t", description="Test field coverage",
            expected_output=ExpectedOutput(fields=fields),
        )

    def test_low_coverage_flags_and_lowers_confidence(self):
        report = ImplementationFactReport(confidence=0.65)
        report.sample_fields = {"stock_news": ["title", "url", "publish_time"]}
        _controller()._validate_expected_field_coverage(
            self._spec_with_fields(["title", "sentiment_score_xyz", "importance_level_xyz"]),
            report, "local_data",
        )
        assert any("Insufficient coverage of acceptance fields" in n for n in report.notes)
        assert any("sentiment_score_xyz" in n for n in report.notes)
        assert report.confidence <= 0.45

    def test_full_coverage_no_warning(self):
        report = ImplementationFactReport(confidence=0.65)
        report.sample_fields = {"stock_news": ["title", "url"]}
        _controller()._validate_expected_field_coverage(
            self._spec_with_fields(["title", "url"]), report, "local_data",
        )
        assert not any("Insufficient coverage of acceptance fields" in n for n in report.notes)
        assert report.confidence == 0.65

    def test_external_mode_advises_without_local_check(self):
        """external_api Mode: The field comes from the external interface. It only prompts for verification and does not score based on local coverage."""
        report = ImplementationFactReport(confidence=0.65)
        _controller()._validate_expected_field_coverage(
            self._spec_with_fields(["model_id", "model_name", "manufacturer_id"]),
            report, "external_api",
        )
        assert any("The actual response from the external interface shall prevail." in n for n in report.notes)
        assert report.confidence == 0.65

    def test_no_expected_fields_is_noop(self):
        report = ImplementationFactReport(confidence=0.65)
        _controller()._validate_expected_field_coverage(
            self._spec_with_fields([]), report, "local_data",
        )
        assert report.notes == []
        assert report.confidence == 0.65
