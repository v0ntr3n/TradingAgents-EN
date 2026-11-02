# -*- coding: utf-8 -*-
"""CodeGenerator system prompt Inject tests on demand.

Verify the tailoring of system prompt by requirement type shunt (external_api/local_data):
- external_api (External interface integration, such as knowing Chedi): Do not inject local stock data asset documents
- local_data (Default): Use compact API index instead of full API documentation
"""

import pytest

from core.tools.external.code_generator import (
    CODING_PATTERNS,
    EXTERNAL_API_RULES,
    LOCAL_DATA_API_INDEX,
    PROJECT_ACCESS_INDEX,
    CodeGenerator,
)
from core.tools.external.iteration_controller import IterationController
from core.tools.external.requirement_analyzer import classify_requirement_mode
from core.tools.external.skill_spec import SkillSpec


def _make_spec(**overrides) -> SkillSpec:
    kwargs = dict(
        tool_id="probe_test",
        display_name="Probe test",
        description="Query the operating income and net profit trends of a certain A-share in the past five years",
        category="fundamentals",
        data_source="tushare",
        parameters=[{"name": "symbol", "type": "string", "description": "Stock code", "required": True}],
        expected_output={"fields": ["symbol", "years", "revenue"]},
    )
    kwargs.update(overrides)
    return SkillSpec(**kwargs)


@pytest.fixture()
def generator() -> CodeGenerator:
    return CodeGenerator()


# ---------- external_api mode ----------

class TestExternalApiPrompt:
    def test_dongchedi_spec_classified_as_external_api(self):
        spec = _make_spec(
            tool_id="dongchedi_manufacturer_model_monthly_sales",
            display_name="Understand the monthly sales of car manufacturers models",
            description="Obtain the monthly sales data of the specified manufacturer s models from the Qianchedi interface",
            data_source="dongchedi",
            category="market",
        )
        assert classify_requirement_mode(spec) == "external_api"

    def test_external_api_prompt_excludes_local_assets(self, generator):
        """External interface requirements: local stock data asset documents should not be injected"""
        spec = _make_spec(data_source="dongchedi")
        prompt = generator._build_system_prompt(spec)

        # Local asset content will never be injected
        assert "local data access — API Index" not in prompt
        assert "Project data access — API Index" not in prompt
        assert "Stock data collection" not in prompt
        assert "data contract" not in prompt
        assert "Reference template" not in prompt
        assert "Allows importing the following modules" not in prompt
        assert "Helper The iron law of transparent transmission" not in prompt
        assert "get_stock_basic_info" not in prompt

        # External interface rules and output formats must be preserved
        assert "Key requirements for external interface integration" in prompt
        assert EXTERNAL_API_RULES.strip().splitlines()[1] in prompt
        assert "=== CODE START ===" in prompt
        assert "=== TESTS END ===" in prompt
        # Coding standards retention (universal iron law)
        assert CODING_PATTERNS[:20] in prompt

    def test_external_api_prompt_much_smaller(self, generator):
        """The external interface prompt should be significantly smaller than the local data prompt"""
        ext_prompt = generator._build_system_prompt(_make_spec(data_source="dongchedi"))
        local_prompt = generator._build_system_prompt(_make_spec())
        assert len(ext_prompt) < len(local_prompt) * 0.5

    def test_out_of_catalog_source_drops_catalog_doc(self, generator):
        """Data source outside the directory (dongchedi): Do not inject AKShare/Tushare directory details, instead use out-of-directory integration instructions"""
        prompt = generator._build_system_prompt(_make_spec(data_source="dongchedi"))

        assert "Directory external interface integration" in prompt
        assert "sole source of truth" in prompt
        # Directory details entries are not injected (to avoid inducing LLM to use AKShare/Tushare)
        assert "AKShareProvider" not in prompt
        assert "TushareProvider" not in prompt
        assert "get_akshare_provider" not in prompt

    def test_external_api_user_prompt_skips_factor_catalog(self, generator):
        """External interface requirements: user prompt does not inject stock factor whitelist (MA/RSI/MACD and other irrelevant content)"""
        spec = _make_spec(
            tool_id="dongchedi_car_rank_data",
            display_name="Monthly sales query of car models",
            description="Through the car model sales ranking interface on the PC side of the car, obtain the monthly sales data of national car models according to the specified month or aggregation period.",
            data_source="dongchedi",
            category="market",
            expected_output={"fields": ["rank", "car_model", "monthly_sales"]},
        )
        prompt = generator._build_user_prompt(spec)

        assert "Common analysis factor whitelist" not in prompt
        assert "technical_core" not in prompt
        assert "MACD" not in prompt
        assert "KDJ" not in prompt
        # Local runtime interface constraints are not injected
        assert "Skill Runtime Interface constraints" not in prompt
        assert "core.skill_runtime.data_access" not in prompt
        # ""Switching to akshare/tushare instead" will induce the abandonment of the user-specified interface and replace it with the external interface version
        assert "Switch to free alternatives like akshare, tushare, etc." not in prompt
        assert "No other data source may be used instead" in prompt
        # Simulation constraint retention is strictly prohibited
        assert "Simulation/placeholder is strictly prohibited" in prompt

    def test_local_user_prompt_keeps_runtime_and_factor_sections(self, generator):
        """Local data requirements: retain runtime interface constraints and factor constraints blocks"""
        prompt = generator._build_user_prompt(_make_spec())
        assert "Skill Runtime Interface constraints" in prompt
        assert "Common analysis factor constraints" in prompt


# ---------- local_data mode ----------

class TestLocalDataPrompt:
    def test_local_data_spec_classified_as_local(self):
        assert classify_requirement_mode(_make_spec()) == "local_data"

    def test_local_prompt_uses_compact_index(self, generator):
        """Local data requirements: Compact index replaces full API documentation"""
        prompt = generator._build_system_prompt(_make_spec())

        assert "local data access — API Index" in prompt
        assert "Project data access — API Index" in prompt
        assert "get_stock_valuation_context" in prompt
        assert "get_external_valuation_data" in prompt
        # Core anti-hallucination rules retained
        assert "Helper The iron law of transparent transmission" in prompt
        assert "defensive programming" in prompt

    def test_local_prompt_smaller_than_full_docs(self, generator):
        """The compact index version should be significantly smaller than the old full document version"""
        from core.skill_runtime.data_access import LOCAL_DATA_API_DOC
        from core.skill_runtime.project_access import PROJECT_DATA_ACCESS_DOC

        prompt = generator._build_system_prompt(_make_spec())
        # Restore the equivalent size of the old version (full document replacement index) for comparison
        old_equivalent = (
            len(prompt)
            + len(LOCAL_DATA_API_DOC) + len(PROJECT_DATA_ACCESS_DOC)
            - len(LOCAL_DATA_API_INDEX) - len(PROJECT_ACCESS_INDEX)
        )
        assert len(prompt) < old_equivalent - 4000

    def test_index_constants_are_compact(self):
        """The index constant itself remains compact (significantly smaller than the corresponding full document)"""
        from core.skill_runtime.data_access import LOCAL_DATA_API_DOC
        from core.skill_runtime.project_access import PROJECT_DATA_ACCESS_DOC

        assert len(LOCAL_DATA_API_INDEX) < len(LOCAL_DATA_API_DOC) * 0.5
        assert len(PROJECT_ACCESS_INDEX) < len(PROJECT_DATA_ACCESS_DOC) * 0.5


# ---------- Agent Loop Coordinator prompt diversion ----------

class TestAgenticSystemPrompt:
    def test_external_api_prompt_drops_stock_assumptions(self):
        """External interface requirements: Agent Loop prompt should not include local assumptions such as stock preflight/helper reuse"""
        spec = _make_spec(data_source="dongchedi")
        prompt = IterationController._build_agentic_system_prompt(spec)

        assert "External interface integration" in prompt
        # Local data is assumed to be eliminated
        assert "get_stock_basic_info" not in prompt
        assert "Data source label usage rules" not in prompt
        assert "Must reuse existing tools" not in prompt
        assert "list_analysis_tools" not in prompt
        assert "Stock code preflight" not in prompt
        # External interface defense rules retained
        assert "Parameter defense" in prompt
        assert "timeout=10" in prompt
        assert "pipeline_tool" in prompt

    def test_local_data_prompt_keeps_stock_rules(self):
        """Local data requirements: Agent Loop prompt retains stock preflight/helper reuse rules"""
        prompt = IterationController._build_agentic_system_prompt(_make_spec())
        assert "get_stock_basic_info" in prompt
        assert "Data source label usage rules" in prompt
        assert "Must reuse existing tools" in prompt
        assert "list_analysis_tools" in prompt
        assert "Stock code preflight" in prompt

    def test_no_spec_defaults_to_local(self):
        """When spec is not passed, the local_data branch defaults (backwards compatible)"""
        prompt = IterationController._build_agentic_system_prompt(None)
        assert "get_stock_basic_info" in prompt


# ---------- Interface preflight measured fact injection (spec.metadata.interface_preflight → user prompt)  ----------

_VERIFIED_PREFLIGHT = {
    "status": "verified",
    "http_status": 200,
    "data_items": 10,
    "sample_fields": ["series_id", "series_name", "rank", "min_price", "max_price"],
    # Baseline query parameters (documented); brand_name was determined to be ignored by the interface after differential testing
    "probed_params": {"month": "202608", "rank_data_type": 11, "count": 100, "offset": 0},
    "ignored_params": ["brand_name"],
    "url": "https://www.dongchedi.com/motor/pc/car/rank_data",
    "checked_at": "2026-09-15T10:00:00",
}


class TestPreflightFactsBlock:
    def _preflight_spec(self, preflight) -> SkillSpec:
        return _make_spec(
            tool_id="dongchedi_car_rank_data",
            display_name="Monthly sales query of car models",
            description="Through the car model sales ranking interface on the PC side of the car, obtain the monthly sales data of national car models according to the specified month or aggregation period.",
            data_source="dongchedi",
            category="market",
            metadata={"interface_preflight": preflight},
        )

    def test_verified_preflight_injects_real_fields_and_params(self, generator):
        """verified Preflight: Measured URLs/real fields/baseline parameters are all injected into the block"""
        block = generator._build_preflight_facts_block(self._preflight_spec(_VERIFIED_PREFLIGHT))

        assert "Interface measured facts" in block
        assert "https://www.dongchedi.com/motor/pc/car/rank_data" in block
        assert "series_name" in block and "min_price" in block
        assert "month='202608'" in block
        assert "Return the number of data items: 10" in block
        # brand_name It is an ignored parameter and is not among the measured available query parameters.
        assert "brand_name" not in block.split("Available query parameters verified by actual testing")[1].split("\n")[0]

    def test_verified_block_contains_local_filter_rule(self, generator):
        """Core rule: Business filtering parameters are not included in the measured query parameters → Do not spell the URL. Pull the full volume and then filter it locally."""
        block = generator._build_preflight_facts_block(self._preflight_spec(_VERIFIED_PREFLIGHT))

        assert "brand" in block
        assert "fight in URL" in block
        assert "local implementation" in block
        # It is strictly prohibited to make up field rules
        assert "It is strictly prohibited to make up field names" in block

    def test_ignored_params_get_dedicated_rule(self, generator):
        """Differential test output ignored_params → Exclusive rules name this parameter"""
        block = generator._build_preflight_facts_block(self._preflight_spec(_VERIFIED_PREFLIGHT))

        assert "Ignored by interface" in block
        assert "brand_name" in block
        # Roll call rules + local filtering instructions
        assert "Fighting is strictly prohibited URL" in block
        assert "series_name" in block  # Return fields for brand matching

    def test_server_filter_params_allowed_in_url(self, generator):
        """Differential test output server_filter_params → Tips can be used as URL query parameters"""
        preflight = dict(_VERIFIED_PREFLIGHT)
        preflight.pop("ignored_params")
        preflight["server_filter_params"] = ["brand_name"]
        block = generator._build_preflight_facts_block(self._preflight_spec(preflight))

        assert "Server-side filtering seems to be taking effect" in block
        assert "Can be used as URL query parameters" in block
        # Use general rules when there is no ignored_params (it is still prohibited to invent other filter parameters)
        assert "Fictitious interface query parameters" in block

    def test_ignored_param_without_matching_field_gets_boundary_rule(self, generator):
        """The ignored parameter has no corresponding field in the return field. → Inject data boundary rules (data-driven, not hard-coded by keywords).

        brand_name Ignored by actual measurement, there are no fields related to names in sample_fields → Boundary rules.
        """
        block = generator._build_preflight_facts_block(self._preflight_spec(_VERIFIED_PREFLIGHT))

        assert "There is no field corresponding to brand_name" in block
        assert "Results may be incomplete" in block
        assert "It is strictly prohibited to create new interface endpoints" in block

    def test_ignored_param_with_matching_field_no_boundary_rule(self, generator):
        """The ignored parameters have corresponding fields in the return fields (brand_name ↔ brand_name) → no boundary rules"""
        preflight = dict(_VERIFIED_PREFLIGHT)
        preflight["sample_fields"] = ["series_id", "series_name", "brand_name", "rank"]
        block = generator._build_preflight_facts_block(self._preflight_spec(preflight))

        assert "does not exist with" not in block

    def test_boundary_rule_data_driven_any_filter(self, generator):
        """Boundary rules have nothing to do with the business domain: the same is true if another ignored parameter (city) is used"""
        preflight = dict(_VERIFIED_PREFLIGHT)
        preflight["ignored_params"] = ["city"]
        block = generator._build_preflight_facts_block(self._preflight_spec(preflight))

        assert "There is no field corresponding to city" in block

    def test_warning_preflight_uses_structural_caution(self, generator):
        """warning Preflight (interface reachable but structure unexplored): Inject structure detection warnings instead of field lists"""
        preflight = {
            "status": "warning",
            "http_status": 200,
            "message": "Interface reachable (HTTP 200, JSON response), but no data entry recognized",
            "url": "https://example.com/api/data",
        }
        block = generator._build_preflight_facts_block(self._preflight_spec(preflight))

        assert "Data entry not recognized" in block
        assert "JSON top key" in block
        assert "local" in block  # Filtering still needs to be implemented locally

    def test_no_preflight_no_block(self, generator):
        """No preflight results (local_data / preflight not run): block is not injected"""
        assert generator._build_preflight_facts_block(_make_spec()) == ""
        assert generator._build_preflight_facts_block(
            self._preflight_spec({"status": "verified"})  # No url is considered invalid
        ) == ""

    def test_user_prompt_includes_preflight_block(self, generator):
        """Integration: Test fact blocks and real fields appear in the user prompt"""
        prompt = generator._build_user_prompt(self._preflight_spec(_VERIFIED_PREFLIGHT))

        assert "Interface measured facts" in prompt
        assert "series_name" in prompt
        # Does not appear in prompt when there is no preflight
        plain_prompt = generator._build_user_prompt(
            _make_spec(data_source="dongchedi")
        )
        assert "Interface measured facts" not in plain_prompt

    def test_agentic_task_prompt_includes_preflight_block(self):
        """Agent Loop The coordinator task prompt is also injected into the measured fact block (feedback guidance does not go astray)"""
        prompt = IterationController._build_agentic_task_prompt(
            self._preflight_spec(_VERIFIED_PREFLIGHT), "", None
        )

        assert "Interface measured facts" in prompt
        assert "Ignored by interface" in prompt
        assert "brand_name" in prompt
        assert "local implementation" in prompt
        # No blocks without preflight
        plain = IterationController._build_agentic_task_prompt(
            _make_spec(data_source="dongchedi"), "", None
        )
        assert "Interface measured facts" not in plain


# ---------- Version Upgrade: Parent Code Baseline + minimum change order ----------

_PARENT_CODE = '''"""Parent version: Understanding Chedi car model sales inquiry (verified)"""
import requests

RANK_URL = "https://www.dongchedi.com/motor/pc/car/rank_data"


def parent_tool(brand: str = "BYD", month: str = "202608"):
    params = {"month": month, "rank_data_type": "11", "count": "100", "offset": "0"}
    resp = requests.get(RANK_URL, params=params, timeout=10)
    records = resp.json().get("data", {}).get("list", [])
    matched = [r for r in records if brand in (r.get("series_name") or "")]
    return {"status": "success", "data": matched}
'''


class TestUpgradeModePrompt:
    def test_upgrade_block_with_parent_code_and_no_feedback(self, generator):
        """Upgrade mode: with parent code and no failure feedback → Upgrade blocks instead of repair blocks"""
        prompt = generator._build_user_prompt(
            _make_spec(tool_id="parent_tool_v2"),
            feedback="",
            previous_code=_PARENT_CODE,
            iteration_mode="upgrade",
        )

        assert "Version upgrade" in prompt
        assert "make minimal changes" in prompt
        assert "Rewriting from scratch is strictly prohibited" in prompt
        # Parent code is shown as a baseline
        assert "Current version code (has been verified and is the baseline for this upgrade)" in prompt
        assert "rank_data" in prompt
        # Don't misuse repair block copy
        assert "Iterative repair" not in prompt

    def test_upgrade_block_rules_cover_minimal_change(self, generator):
        """The upgrade block contains rules such as retaining verified logic/no redesign/function names subject to new specifications."""
        prompt = generator._build_user_prompt(
            _make_spec(tool_id="parent_tool_v2"),
            feedback="Add a new price_level field",
            previous_code=_PARENT_CODE,
            iteration_mode="upgrade",
        )

        assert "Keep verified logic" in prompt
        assert "No redesign" in prompt
        assert "The function name is subject to the new specifications" in prompt
        assert "parent_tool_v2" in prompt  # New spec function names appear in spec JSON
        # The upgrade requirement text is also injected
        assert "price_level" in prompt

    def test_repair_mode_keeps_original_fix_block(self, generator):
        """Return: repair mode is still a directed repair block"""
        prompt = generator._build_user_prompt(
            _make_spec(),
            feedback="Sandbox execution 404: URL rewritten",
            previous_code=_PARENT_CODE,
            iteration_mode="repair",
        )

        assert "Iterative repair" in prompt
        assert "directed repair" in prompt
        assert "Version upgrade" not in prompt

    def test_no_previous_code_no_iteration_block(self, generator):
        """Regression: no iteration block appears when there is no parent code/no previous round code"""
        prompt = generator._build_user_prompt(
            _make_spec(), feedback="", previous_code="", iteration_mode="upgrade"
        )

        assert "Version upgrade" not in prompt
        assert "Iterative repair" not in prompt

    def test_agentic_task_prompt_upgrade_carries_parent_code(self):
        """Coordinator task prompt: Upgrade with parent code baseline and minimum change planning requirements"""
        prompt = IterationController._build_agentic_task_prompt(
            _make_spec(tool_id="parent_tool_v2"),
            "",
            None,
            parent_code=_PARENT_CODE,
        )

        assert "Version upgrade tasks" in prompt
        assert "Not generated from scratch" in prompt
        assert "rank_data" in prompt
        # Coordinators are asked to plan only point-of-difference changes
        assert "Difference" in prompt and "Reserve" in prompt

    def test_agentic_task_prompt_without_parent_code_no_upgrade_block(self):
        """Return: non-upgrade scene coordinator prompt does not include upgrade blocks"""
        prompt = IterationController._build_agentic_task_prompt(
            _make_spec(), "", None
        )
        assert "Version upgrade tasks" not in prompt
