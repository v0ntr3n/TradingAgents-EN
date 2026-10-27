# -*- coding: utf-8 -*-
"""business acceptor list[dict] Output supported single tests.

Background (dongchedi accident scene): Generated Skill button spec.expected_output.type="list[dict]"
The record list is returned correctly (month/rank/manufacturer_name/model_name/sales_volume are all non-empty),
But the two dict assumptions of DefaultBusinessVerifier put the correct implementation into error:
① _resolve_target Return directly to list output None → required_field All misjudgments failed;
② status_success Only recognizes dict(output.get("status")) → list The output must fail.
Resulting in the 2nd/3rd round of iterations when the output is completely correct business_score=3.0, passed=False. 
"""
from core.tools.external.business_verifier import DefaultBusinessVerifier
from core.tools.external.skill_spec import (
    ExpectedOutput,
    SandboxResult,
    SkillSpec,
    ValidationCheck,
)


def _verifier() -> DefaultBusinessVerifier:
    # Do not pass provider: LLM business acceptance skips, focusing on pure rule behavior
    return DefaultBusinessVerifier(llm_client=None, provider=None)


def _dongchedi_spec() -> SkillSpec:
    return SkillSpec(
        tool_id="dongchedi_manufacturer_model_monthly_sales",
        display_name="Understanding Chedi s vehicle model monthly sales data query tool",
        description="Call the national car sales list interface disclosed by CHEDI to obtain the monthly sales and ranking information of the designated manufacturer s models.",
        category="utility",
        data_source="dongchedi",
        expected_output=ExpectedOutput(
            type="list[dict]",
            fields=["month", "rank", "manufacturer_name", "model_name", "sales_volume", "raw_data"],
        ),
        validation_checks=[
            ValidationCheck(
                name="status_success",
                description="Interface requests and data processing must be successful and no exceptions are thrown.",
                check_type="status_success",
                rule_level="output",
                blocking=True,
                value_path="output",
                forbid_null=False,
            ),
            *[
                ValidationCheck(
                    name=f"required_field:{f}",
                    description=f"The value of each record when output is successful{f}The field cannot be missing and is not empty",
                    check_type="required_field",
                    rule_level="data",
                    blocking=True,
                    field=f,
                    value_path="data",
                    forbid_null=True,
                )
                for f in ("month", "rank", "manufacturer_name", "model_name", "sales_volume", "raw_data")
            ],
        ],
    )


def _dongchedi_output():
    return [
        {
            "month": "202608", "rank": 1, "manufacturer_name": "Geely Galaxy",
            "model_name": "star wish", "sales_volume": 39651,
            "raw_data": {"series_id": 20154, "count": 39651, "brand_name": "Geely Galaxy"},
        },
        {
            "month": "202608", "rank": 2, "manufacturer_name": "Leap car",
            "model_name": "Zero run A10", "sales_volume": 30652,
            "raw_data": {"series_id": 9267, "count": 30652, "brand_name": "Leap car"},
        },
    ]


class TestListDictOutput:
    """list[dict] Acceptance behavior for the output (in this case spec.expected_output.type)."""

    def test_correct_list_output_passes_all_checks(self):
        """Accident scene reproduction: the output is completely correct list[dict] All acceptances must be passed."""
        result = _verifier().verify(
            SandboxResult(success=True, output=_dongchedi_output()),
            _dongchedi_spec(),
        )
        assert result.passed is True
        assert result.business_score == 10.0
        assert result.failures == []

    def test_empty_list_fails_field_checks(self):
        result = _verifier().verify(
            SandboxResult(success=True, output=[]),
            _dongchedi_spec(),
        )
        assert result.passed is False
        # Empty list: status is considered successful, but field check failed (no structured object to check)
        assert any(f.rule_id.startswith("required_field") for f in result.failures)

    def test_list_first_record_missing_field_fails(self):
        output = _dongchedi_output()
        output[0].pop("month")
        result = _verifier().verify(SandboxResult(success=True, output=output), _dongchedi_spec())
        assert result.passed is False
        assert any("month" in f.message for f in result.failures)

    def test_list_first_record_null_field_fails(self):
        output = _dongchedi_output()
        output[0]["sales_volume"] = None
        result = _verifier().verify(SandboxResult(success=True, output=output), _dongchedi_spec())
        assert result.passed is False
        assert any("sales_volume" in f.message for f in result.failures)


class TestPlausibilityRawDataExclusion:
    """raw_data The original echo does not participate in the numerical rationality check (dongchedi No. 2~6 Round manslaughter fix).

    Accident scene: interface noise field in raw_data (score/descender_price list mode is always 0)
    is collected recursively as"trend sequence"value, trigger'All the data in the list are 0'Misjudgment.
    """

    @staticmethod
    def _spec() -> SkillSpec:
        return SkillSpec(
            tool_id="dongchedi_car_model_monthly_sales",
            display_name="t",
            description="Monthly sales query of car models",
        )

    def test_raw_data_zero_noise_not_flagged(self):
        """raw_data Constant zero noise must not trigger all-zero misjudgments (the real business value should pass if it is not zero)."""
        output = {
            "status": "success", "query_period": "202608", "count": 10, "offset": 0,
            "data": [
                {"query_period": "202608", "rank": i + 1, "model_name": f"m{i}",
                 "manufacturer_name": "Manufacturer", "sales": 30000 - i * 100,
                 "raw_data": {"score": 0, "descender_price": 0, "count": 30000 - i * 100}}
                for i in range(10)
            ],
        }
        result = _verifier().verify(SandboxResult(success=True, output=output), self._spec())
        assert result.passed is True
        assert not any(
            f.rule_id in ("trend_list_all_zeros", "all_zero_values") for f in result.failures
        )

    def test_top_level_all_zero_still_flagged(self):
        """Top-level business fields that are all zero should still be intercepted (the rationality check ontology does not fail)."""
        output = {
            "status": "success",
            "data": [{"rank": 0, "sales": 0, "volume": 0} for _ in range(3)],
        }
        result = _verifier().verify(SandboxResult(success=True, output=output), self._spec())
        assert any(
            f.rule_id in ("trend_list_all_zeros", "all_zero_values") for f in result.failures
        )


class TestDictOutputRegression:
    """dict Regression of existing behavior of output (fixes must not change)."""

    def test_dict_with_status_and_data_passes(self):
        spec = _dongchedi_spec()
        spec.expected_output = ExpectedOutput(type="dict", fields=["month", "sales_volume"])
        spec.validation_checks = [
            ValidationCheck(name="status_success", check_type="status_success",
                            rule_level="output", value_path="output"),
            ValidationCheck(name="required_field:month", check_type="required_field",
                            rule_level="data", field="month", value_path="data", forbid_null=True),
        ]
        result = _verifier().verify(
            SandboxResult(success=True, output={"status": "success", "data": [{"month": "202608", "sales_volume": 1}]}),
            spec,
        )
        assert result.passed is True

    def test_dict_error_status_still_fails(self):
        spec = _dongchedi_spec()
        spec.validation_checks = [
            ValidationCheck(name="status_success", check_type="status_success",
                            rule_level="output", value_path="output"),
        ]
        result = _verifier().verify(
            SandboxResult(success=True, output={"status": "error", "message": "boom"}),
            spec,
        )
        assert result.passed is False
        assert any(f.rule_id == "status_success" for f in result.failures)

    def test_flat_dict_fallback_target_unchanged(self):
        """Flat dict (without value_path nested key) falls back to the existing behavior of output itself."""
        spec = _dongchedi_spec()
        spec.validation_checks = [
            ValidationCheck(name="required_field:month", check_type="required_field",
                            rule_level="data", field="month", value_path="data", forbid_null=True),
        ]
        result = _verifier().verify(
            SandboxResult(success=True, output={"month": "202608", "sales_volume": 39651}),
            spec,
        )
        assert result.passed is True

    def test_sandbox_failure_short_circuits(self):
        result = _verifier().verify(
            SandboxResult(success=False, error="boom"),
            _dongchedi_spec(),
        )
        assert result.passed is False
        assert result.business_score == 0.0
