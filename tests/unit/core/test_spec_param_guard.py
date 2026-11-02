# -*- coding: utf-8 -*-
"""Line of defense testing for illegal identifier parameters (e.g. headers.User-Agent).

Background: During the requirements analysis phase, LLM mistakenly included HTTP request headers as function parameters.
 (headers.User-Agent / headers.Referer) , Such names cannot appear in
Python In the function signature, the static verification will fail in every round and the Agent Loop will retry in an infinite loop.
"""

import pytest

from core.tools.external.requirement_analyzer import RequirementAnalyzer
from core.tools.external.skill_spec import GeneratedCode, SkillSpec
from core.tools.external.static_validator import StaticValidator

DCD_URL = "https://www.dongchedi.com/motor/pc/car/rank_data"


def _make_spec(params: list) -> SkillSpec:
    return SkillSpec(
        tool_id="probe_tool",
        display_name="probe",
        description="test",
        category="market",
        data_source="dongchedi",
        parameters=params,
    )


class TestStaticValidatorInvalidParams:
    def test_invalid_param_names_skipped_in_signature_check(self):
        """When pseudo-parameters such as headers.User-Agent are included, signature comparison should be skipped instead of reporting an error."""
        spec = _make_spec([
            {"name": "month", "type": "string", "description": "month", "required": True},
            {"name": "headers.User-Agent", "type": "string", "description": "UA", "required": True},
            {"name": "headers.Referer", "type": "string", "description": "Referer", "required": True},
        ])
        code = GeneratedCode(
            code="def probe_tool(month: str = '202608'):\n    return {'status': 'success', 'data': []}\n",
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert result.passed, f"Should pass static verification, error: {result.errors}"
        assert not any("headers" in e for e in result.errors)

    def test_python_keyword_params_skipped_in_signature_check(self):
        """Python Keyword parameters (class/import) also cannot appear in the signature and should be skipped"""
        spec = _make_spec([
            {"name": "month", "type": "string", "description": "month", "required": True},
            {"name": "class", "type": "string", "description": "Category", "required": True},
            {"name": "import", "type": "string", "description": "import", "required": True},
        ])
        code = GeneratedCode(
            code="def probe_tool(month: str = '202608'):\n    return {'status': 'success', 'data': []}\n",
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert result.passed, f"Should pass static verification, error: {result.errors}"

    def test_valid_missing_param_still_reported(self):
        """When legal parameters are missing, an error should still be reported normally (the defense line does not exempt true missing)"""
        spec = _make_spec([
            {"name": "month", "type": "string", "description": "month", "required": True},
            {"name": "count", "type": "int", "description": "Quantity", "required": True},
        ])
        code = GeneratedCode(
            code="def probe_tool(month: str = '202608'):\n    return {'status': 'success', 'data': []}\n",
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert not result.passed
        assert any("count" in e for e in result.errors)


class TestSpecParamSanitizer:
    def test_sanitize_drops_invalid_params_and_adds_constraint(self):
        """Pseudo-parameters are eliminated, and header requirements are transferred to constraints without losing information."""
        data = {
            "tool_id": "t",
            "parameters": [
                {"name": "month", "type": "string", "description": "month", "required": True},
                {"name": "headers.User-Agent", "type": "string", "description": "UA", "required": True},
                {"name": "headers.Referer", "type": "string", "description": "R", "required": True},
            ],
            "constraints": ["Original constraints"],
        }
        RequirementAnalyzer._sanitize_spec_params(data)
        assert [p["name"] for p in data["parameters"]] == ["month"]
        assert len(data["constraints"]) == 2
        assert "HTTP head" in data["constraints"][1]

    def test_sanitize_noop_for_valid_params(self):
        """No modifications are made when the parameters are all legal."""
        data = {
            "tool_id": "t",
            "parameters": [{"name": "month", "type": "string", "description": "m", "required": True}],
            "constraints": ["c"],
        }
        RequirementAnalyzer._sanitize_spec_params(data)
        assert len(data["parameters"]) == 1
        assert data["constraints"] == ["c"]

    def test_sanitize_drops_python_keyword_params(self):
        """Python Keyword arguments (class) are also eliminated"""
        data = {
            "tool_id": "t",
            "parameters": [
                {"name": "month", "type": "string", "description": "m", "required": True},
                {"name": "class", "type": "string", "description": "Category", "required": True},
            ],
            "constraints": [],
        }
        RequirementAnalyzer._sanitize_spec_params(data)
        assert [p["name"] for p in data["parameters"]] == ["month"]
        assert len(data["constraints"]) == 1


class TestInterfaceSpecGuard:
    """Interface specification (URL) full-link defense line from conversation to code"""

    CONVERSATION = (
        "User needs: Understand monthly sales inquiries of Chedi models\n"
        f"GET `{DCD_URL}?month=202608&rank_data_type=11&count=100&offset=0`\n"
        "Request header:User-Agent + Referer That s it, no authentication required.\n"
    )

    def test_ensure_interface_spec_constraints_extracts_url(self):
        """When the conversation contains a URL but the LLM output constraints are empty, the URL and request headers are written in full"""
        data = {"tool_id": "t", "parameters": [], "constraints": []}
        RequirementAnalyzer._ensure_interface_spec_constraints(data, self.CONVERSATION)
        joined = "\n".join(data["constraints"])
        assert DCD_URL in joined
        assert "Rewriting is strictly prohibited" in joined
        assert "User-Agent" in joined

    def test_ensure_interface_spec_constraints_extracts_query_params(self):
        """When the conversation URL contains a query string, the query string is written separately as a documented query parameter constraint (differential detection basis)"""
        data = {"tool_id": "t", "parameters": [], "constraints": []}
        RequirementAnalyzer._ensure_interface_spec_constraints(data, self.CONVERSATION)
        joined = "\n".join(data["constraints"])
        # URL The contract is still the base address (word-for-word comparison is not affected by the query string)
        assert f"interface URL: {DCD_URL}" in joined
        # Keep the query string as is + Local filtering rule tips
        assert "Interface query parameters (user URL original query string): month=202608&rank_data_type=11&count=100&offset=0" in joined
        assert "local filtering" in joined

    def test_ensure_query_params_idempotent(self):
        """The query string is not written repeatedly when it is already in constraints"""
        data = {
            "tool_id": "t",
            "parameters": [],
            "constraints": [
                " [Interface specifications] Interface query parameters (user URL original query string): "
                "month=202608&rank_data_type=11&count=100&offset=0——Only these parameters named interface real query parameters",
            ],
        }
        RequirementAnalyzer._ensure_interface_spec_constraints(data, self.CONVERSATION)
        query_lines = [c for c in data["constraints"] if "Interface query parameters" in c]
        assert len(query_lines) == 1

    def test_ensure_interface_spec_constraints_noop_when_present(self):
        """constraints Do not write repeatedly when the URL is already included"""
        data = {
            "tool_id": "t",
            "parameters": [],
            "constraints": [f"interface address {DCD_URL} Call as is"],
        }
        RequirementAnalyzer._ensure_interface_spec_constraints(data, self.CONVERSATION)
        url_lines = [c for c in data["constraints"] if DCD_URL in c]
        assert len(url_lines) == 1

    def test_ensure_interface_spec_constraints_no_url_noop(self):
        """No constraints are written when the conversation has no URL."""
        data = {"tool_id": "t", "parameters": [], "constraints": []}
        RequirementAnalyzer._ensure_interface_spec_constraints(data, "Local stock data requirements, no external interface")
        assert data["constraints"] == []

    def _spec_with_url_constraint(self) -> SkillSpec:
        return _make_spec([
            {"name": "month", "type": "string", "description": "month", "required": True},
        ]).model_copy(
            update={"constraints": [f" [Interface specifications] Interface URL: {DCD_URL}, Rewriting is strictly prohibited"]}
        )

    def test_static_validator_catches_url_rewrite(self):
        """When the code writes rank_data as rank/data, static verification must be intercepted"""
        spec = self._spec_with_url_constraint()
        code = GeneratedCode(
            code=(
                "def probe_tool(month: str = '202608'):\n"
                "    url = 'https://www.dongchedi.com/motor/pc/car/rank/data'\n"
                "    return {'status': 'success', 'data': []}\n"
            ),
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert not result.passed
        assert any("Interface URL rewriting violation" in e and DCD_URL in e for e in result.errors)

    def test_static_validator_passes_verbatim_url(self):
        """URL Verification passes when used verbatim"""
        spec = self._spec_with_url_constraint()
        code = GeneratedCode(
            code=(
                f"API_URL = \"{DCD_URL}\"\n"
                "def probe_tool(month: str = '202608'):\n"
                "    return {'status': 'success', 'data': []}\n"
            ),
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert result.passed, f"Should pass static verification, error: {result.errors}"

    def test_static_validator_catches_invented_endpoint(self):
        """Static verification must intercept when the code creates endpoints outside the specification (such as brand/all brand resolution)"""
        spec = self._spec_with_url_constraint()
        code = GeneratedCode(
            code=(
                f"API_URL = \"{DCD_URL}\"\n"
                "BRAND_URL = 'https://www.dongchedi.com/motor/pc/car/brand/all'\n"
                "def probe_tool(month: str = '202608'):\n"
                "    return {'status': 'success', 'data': []}\n"
            ),
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert not result.passed
        assert any("Fabricated interface endpoint violation" in e and "brand/all" in e for e in result.errors)

    def test_url_glued_to_chinese_text_not_polluted(self):
        """When the URL in the constraint text is followed by Chinese characters (such as rank_data making a request), it must be truncated and the correct code must not be accidentally killed."""
        spec = _make_spec([
            {"name": "month", "type": "string", "description": "month", "required": True},
        ]).model_copy(
            update={"constraints": [f"can only pass {DCD_URL}] Initiate a GET request, the request header must contain User-Agent"]}
        )
        code = GeneratedCode(
            code=(
                f"API_URL = \"{DCD_URL}\"\n"
                "def probe_tool(month: str = '202608'):\n"
                "    return {'status': 'success', 'data': []}\n"
            ),
            metadata={"tool_id": "probe_tool", "name": "probe", "description": "", "category": "market"},
            tests=[],
        )
        result = StaticValidator().validate(code, spec)
        assert result.passed, f"URL Correct but blocked: {result.errors}"

    def test_conversation_url_glued_to_chinese_extracts_clean(self):
        """When the URL in the original text of the conversation is followed by Chinese characters, a clean URL"""
        data = {"tool_id": "t", "parameters": [], "constraints": []}
        conversation = f"Please request directly{DCD_URL}Initiate a GET call with User-Agent"
        RequirementAnalyzer._ensure_interface_spec_constraints(data, conversation)
        joined = "\n".join(data["constraints"])
        assert DCD_URL in joined
        assert f"{DCD_URL}initiate" not in joined

    def test_codegen_prompt_contains_interface_block(self):
        """user prompt Contains significant areas of interface specifications (including a reminder that rewriting is strictly prohibited)"""
        from core.tools.external.code_generator import CodeGenerator

        spec = self._spec_with_url_constraint()
        gen = CodeGenerator.__new__(CodeGenerator)
        prompt = gen._build_user_prompt(spec)
        assert "Interface specifications — sole source of truth" in prompt
        assert DCD_URL in prompt
        assert "strictly prohibited" in prompt
