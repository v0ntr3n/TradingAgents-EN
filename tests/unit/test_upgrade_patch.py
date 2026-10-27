# -*- coding: utf-8 -*-
"""Upgrade patch mode (upgrade_patch) unit test.

Core regression: The upgrade session had multiple rounds of verification of the parent version `rank_data_type: int = 11`
Rewrite the string monthly sales list and send it directly to the interface, and the interface silently rolls back the popularity list.
The business verification determined that monthly sales of 1.02 million vehicles was unreasonable, resulting in an endless loop of 4 attempts.
In patch mode, LLM only outputs delta, and unmentioned fields are represented by apply_upgrade_patch
Inherit unchanged from parent contract——There is no output channel even if you want to rewrite it.
"""

import json

from core.tools.external.requirement_analyzer import RequirementAnalyzer
from core.tools.external.upgrade_patch import (
    apply_upgrade_patch,
    build_upgrade_patch_prompt,
)


def _parent_contract() -> dict:
    """Parent version contract: real scene (Understanding Car Emperor Monthly Sales List v1, after passing multiple rounds of verification, it will be dropped into the warehouse)"""
    return {
        "tool_id": "dongchedi_car_monthly_sales_rank",
        "root_tool_id": "dongchedi_car_monthly_sales_rank",
        "new_tool_id": "dongchedi_car_monthly_sales_rank_v2",
        "new_version": 2,
        "display_name": "Monthly sales query of car models",
        "description": "Obtain national monthly sales data of vehicle models through the car model sales ranking interface on the PC version of DianCheDi",
        "category": "market",
        "data_source": "dongchedi",
        "parameters": [
            {"name": "month", "type": "string", "description": "month YYYYMM", "required": True, "default": None, "enum": None},
            {"name": "rank_data_type", "type": "integer", "description": "List type, fixed to 11, indicating the national monthly sales list", "required": True, "default": None, "enum": None},
            {"name": "count", "type": "integer", "description": "Number of items returned at a time, default 100", "required": False, "default": None, "enum": None},
            {"name": "offset", "type": "integer", "description": "Page turning offset", "required": False, "default": None, "enum": None},
        ],
        "expected_output": {
            "type": "list[dict]",
            "fields": ["rank", "model_name", "brand", "sales_volume", "month"],
            "description": "Car model monthly sales ranking",
        },
        "constraints": [
            " [Interface specifications — The interface must be used as is URL: https://www.dongchedi.com/motor/pc/car/rank_data (Rewriting of the path is strictly prohibited)",
            "The request must carry User-Agent and Referer request headers",
            "rank_data_type It needs to be 11 to obtain the national monthly sales list. The default may be the attention list.",
        ],
        "test_input": {"month": "202501", "rank_data_type": 11},
        "code": (
            "def dongchedi_car_monthly_sales_rank(month='202608', rank_data_type=11, ...):\n"
            "    if rank_data_type != 11:\n"
            "        return _error('INVALID_PARAM', 'rank_data_type Must be an integer 11')\n"
        ),
    }


# Patch for real upgrade needs: only increase the price range and leave the rest unchanged
_PRICE_PATCH = {
    "upgrade_summary": "Output the new selling price range field",
    "change_points": ["Added price_range (manufacturer s guide price range) to the output field"],
    "output_field_changes": {"add": ["price_range"], "remove": []},
    "parameter_changes": {"add": [], "modify": [], "remove": []},
    "constraint_additions": ["If the interface returns a missing price range, price_range is set to an empty string."],
}


class TestApplyUpgradePatch:
    def test_verified_param_contract_cannot_be_rewritten(self):
        """Core regression: patch not mentioned rank_data_type → The new spec is inherited as is int=11 contract.

        The full regeneration mode once rewrote it into a string monthly sales list and sent it directly to the interface.
        The interface silently rolls back to the hot list, causing an infinite loop——There is no output channel for this field in patch mode.
        """
        spec = apply_upgrade_patch(_parent_contract(), dict(_PRICE_PATCH))

        params = {p.name: p for p in spec.parameters}
        assert params["rank_data_type"].type == "integer"
        assert "fixed to 11" in params["rank_data_type"].description
        # count/offset Wait for parent version parameters not to be lost
        assert set(params) == {"month", "rank_data_type", "count", "offset"}

    def test_parent_constraints_inherited_verbatim(self):
        """The parent version interface constraints (URL/request header/value requirements) are inherited as they are without relying on LLM representation."""
        spec = apply_upgrade_patch(_parent_contract(), dict(_PRICE_PATCH))

        joined = "\n".join(spec.constraints)
        assert "https://www.dongchedi.com/motor/pc/car/rank_data" in joined
        assert "rank_data_type Need to be 11" in joined
        assert "User-Agent and Referer" in joined
        # The new constraints in the patch are listed
        assert "price_range Set to empty string" in joined
        # Iteration version description automatically appended
        assert "This Skill is an iteratively optimized version of dongchedi_car_monthly_sales_rank" in joined

    def test_output_fields_add_only(self):
        spec = apply_upgrade_patch(_parent_contract(), dict(_PRICE_PATCH))
        assert spec.expected_output.fields == [
            "rank", "model_name", "brand", "sales_volume", "month", "price_range",
        ]

    def test_version_naming_from_contract(self):
        """tool_id/display_name/The version number is determined by the value calculated by the service layer (consistent with _save_skill)"""
        spec = apply_upgrade_patch(_parent_contract(), dict(_PRICE_PATCH))
        assert spec.tool_id == "dongchedi_car_monthly_sales_rank_v2"
        assert spec.display_name == "Monthly sales query of car models v2"
        assert spec.parent_skill_id == "dongchedi_car_monthly_sales_rank"
        assert spec.version == 2

    def test_display_name_strips_old_suffix(self):
        """If the display name of the parent version already has the v2 suffix, it should be stripped first and then added with the new suffix (v2 → v3 not superimposed)"""
        contract = _parent_contract()
        contract["display_name"] = "Monthly sales query of car models v2"
        contract["new_version"] = 3
        contract["new_tool_id"] = "dongchedi_car_monthly_sales_rank_v3"
        spec = apply_upgrade_patch(contract, dict(_PRICE_PATCH))
        assert spec.display_name == "Monthly sales query of car models v3"

    def test_modify_param_only_touches_listed_fields(self):
        """modify It is a partial update: only the listed fields are changed, and type/default/required is retained as is."""
        patch = {
            "upgrade_summary": "Month parameter description updated",
            "change_points": ["Parameter month description update"],
            "parameter_changes": {
                "add": [],
                "modify": [{"name": "month", "description": "Statistics month, supports 500/1000 aggregate value"}],
                "remove": [],
            },
        }
        spec = apply_upgrade_patch(_parent_contract(), patch)
        month = {p.name: p for p in spec.parameters}["month"]
        assert month.description == "Statistics month, supports 500/1000 aggregate value"
        assert month.type == "string"
        assert month.required is True

    def test_add_and_remove_params(self):
        patch = {
            "upgrade_summary": "Parameter adjustment",
            "change_points": ["New brand", "Delete count"],
            "parameter_changes": {
                "add": [{"name": "brand", "type": "string", "description": "Brand filter", "required": False}],
                "modify": [],
                "remove": ["count"],
            },
        }
        spec = apply_upgrade_patch(_parent_contract(), patch)
        names = {p.name for p in spec.parameters}
        assert "brand" in names
        assert "count" not in names
        assert "rank_data_type" in names  # unmentioned unmoving

    def test_test_input_merge_and_validation_checks(self):
        """test input parent+Sub-merge; acceptance check derived from final output fields (existence check)"""
        patch = {
            "upgrade_summary": "Change test month",
            "change_points": [],
            "test_input_updates": {"month": "202608"},
        }
        spec = apply_upgrade_patch(_parent_contract(), patch)
        assert spec.test_input["month"] == "202608"
        assert spec.test_input["rank_data_type"] == 11  # Parent version value retained

        check_names = [c.name for c in spec.validation_checks]
        assert "status_success" in check_names
        assert "required_field:sales_volume" in check_names
        # Existence check (forbid_null=False) : Allow legal empty values (such as price_range empty string)
        sv_check = next(c for c in spec.validation_checks if c.name == "required_field:sales_volume")
        assert sv_check.forbid_null is False

    def test_change_points_fallback_to_applied_notes(self):
        """LLM When change_points is not given, the actual changes recorded by the application process are used."""
        patch = {"upgrade_summary": "s", "output_field_changes": {"add": ["price_range"]}}
        spec = apply_upgrade_patch(_parent_contract(), patch)
        notes = spec.metadata["upgrade_change_points"]
        assert any("price_range" in n for n in notes)

    def test_change_points_metadata_for_confirm_page(self):
        spec = apply_upgrade_patch(_parent_contract(), dict(_PRICE_PATCH))
        assert spec.metadata["upgrade_mode"] == "patch"
        assert spec.metadata["upgrade_change_points"] == [
            "Added price_range (manufacturer s guide price range) to the output field"
        ]
        assert spec.metadata["upgrade_parent_tool_id"] == "dongchedi_car_monthly_sales_rank"


class TestBuildUpgradePatchPrompt:
    def test_prompt_contains_full_code_and_constraints(self):
        """Read and write: parent version complete code (not truncated)+ All contracts entered prompt"""
        contract = _parent_contract()
        prompt = build_upgrade_patch_prompt(contract, "User: Increase the selling price range")
        assert "rank_data_type != 11" in prompt  # Code key verification logic
        assert "fixed to 11" in prompt               # parameter contract
        assert "rank_data_type Need to be 11" in prompt  # constraint
        assert "Increase selling price range" in prompt
        # The output format is patch JSON, not the full amount. spec
        assert "parameter_changes" in prompt
        assert "No permission to override parent version contract" in prompt

    def test_prompt_contract_json_parseable(self):
        contract = _parent_contract()
        prompt = build_upgrade_patch_prompt(contract, "Upgrade")
        # prompt The contract JSON block in is parsable and contains parameter definitions
        block = prompt.split("```json\n")[1].split("\n```")[0]
        parsed = json.loads(block)
        assert any(p["name"] == "rank_data_type" for p in parsed["parameters"])


class TestAnalyzerRouting:
    def test_generate_spec_routes_to_patch_mode(self, monkeypatch):
        """When parent_contract is passed in, _generate_spec takes priority in patch mode and does not touch the full path."""
        analyzer = RequirementAnalyzer()

        def _fake_upgrade(conversation, parent_contract):
            return apply_upgrade_patch(parent_contract, dict(_PRICE_PATCH))

        def _forbid_full_path(*args, **kwargs):
            raise AssertionError("Should not go to the full spec generation path (patch mode should short-circuit back)")

        monkeypatch.setattr(analyzer, "_generate_upgrade_spec", _fake_upgrade)
        monkeypatch.setattr(analyzer, "_chat_with_quick_fallback", _forbid_full_path)

        spec = analyzer._generate_spec(
            "Conversation content", fact_report=None, session=None,
            parent_contract=_parent_contract(),
        )
        assert spec is not None
        assert spec.metadata["upgrade_mode"] == "patch"
        # Fields not mentioned are inherited from the parent contract
        params = {p.name: p for p in spec.parameters}
        assert params["rank_data_type"].type == "integer"

    def test_generate_spec_falls_back_when_patch_fails(self, monkeypatch):
        """Downgrade to full generation when patch generation fails (parent contract injection prompt)"""
        analyzer = RequirementAnalyzer()

        def _broken_upgrade(conversation, parent_contract):
            return None

        captured = {}

        def _fake_full_chat(messages, stage=""):
            captured["prompt"] = messages[0].content
            return "{}"  # Let full path parsing fail → _raise_analysis_error

        monkeypatch.setattr(analyzer, "_generate_upgrade_spec", _broken_upgrade)
        monkeypatch.setattr(analyzer, "_chat_with_quick_fallback", _fake_full_chat)

        session = type("S", (), {"iterate_skill_id": "dongchedi_car_monthly_sales_rank"})()
        try:
            analyzer._generate_spec(
                "Conversation content", fact_report=None, session=session,
                parent_contract=_parent_contract(),
            )
            raised = False
        except Exception:
            raised = True
        # The full path is walked and the parent contract injects downgrades prompt
        assert raised
        assert "parent version contract" in captured.get("prompt", "")
        assert "fixed to 11" in captured.get("prompt", "")
