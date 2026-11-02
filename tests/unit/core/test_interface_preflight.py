# -*- coding: utf-8 -*-
"""External interface preflight (interface_preflight) unit test.

Verify:
- Extract the interface URL from spec.constraints to construct the detection code (including URL,**kwargs signature, request header)
- Interpretation of sandbox results (verified/warning/failed)
"""

from core.tools.external.interface_preflight import (
    build_interface_probe,
    interpret_probe_result,
    _extract_query_params_from_parent_code,
)
from core.tools.external.skill_spec import SandboxResult, SkillSpec

DCD_URL = "https://www.dongchedi.com/motor/pc/car/rank_data"


def _make_spec(**overrides) -> SkillSpec:
    kwargs = dict(
        tool_id="dongchedi_probe",
        display_name="Understand car detection",
        description="Monthly sales query of car models",
        category="market",
        data_source="dongchedi",
        parameters=[
            {"name": "month", "type": "string", "description": "month", "required": True},
            {"name": "rank_data_type", "type": "int", "description": "List type", "required": False, "default": 11},
        ],
        expected_output={"fields": ["rank", "car_model", "monthly_sales"]},
        constraints=[
            f" [Interface specifications — The interface must be used as is URL: {DCD_URL} (Rewriting of the path is strictly prohibited)",
            "The request must carry User-Agent and Referer request headers",
        ],
        test_input={"month": "202608", "rank_data_type": 11},
    )
    kwargs.update(overrides)
    return SkillSpec(**kwargs)


class TestBuildInterfaceProbe:
    def test_probe_code_contains_url_and_headers(self):
        probe = build_interface_probe(_make_spec())
        assert probe is not None
        assert probe["url"] == DCD_URL
        assert DCD_URL in probe["code"]
        # The function name is consistent with tool_id (the sandbox runner calls it according to tool_id)
        assert "def dongchedi_probe(**kwargs)" in probe["code"]
        # constraints mentioned Referer → Request a headband
        assert "Referer" in probe["code"]
        assert "User-Agent" in probe["code"]
        # The request parameters come from test_input
        assert probe["params"] == {"month": "202608", "rank_data_type": 11}

    def test_probe_uses_param_defaults_without_test_input(self):
        spec = _make_spec(test_input={})
        probe = build_interface_probe(spec)
        assert probe is not None
        assert probe["params"] == {"rank_data_type": 11}

    def test_no_url_constraints_returns_none(self):
        spec = _make_spec(constraints=["Only local data can be used"])
        assert build_interface_probe(spec) is None

    def test_domain_only_url_ignored(self):
        """Pure domain name (no path) is not used as the interface address"""
        spec = _make_spec(constraints=["Reference https://www.dongchedi.com/ Home page"])
        assert build_interface_probe(spec) is None

    def test_url_glued_chinese_truncated(self):
        """URL Truncated when followed by Chinese characters (same set of ASCII regular rules as the validator)"""
        spec = _make_spec(constraints=[f"Must request{DCD_URL}Make a call"])
        probe = build_interface_probe(spec)
        assert probe is not None
        assert probe["url"] == DCD_URL

    def test_documented_query_params_split_baseline_and_filters(self):
        """URL When query string is included: documented parameters are entered into the baseline, and other parameters (such as brand_name) are used for differential testing."""
        spec = _make_spec(
            constraints=[
                " [Interface specifications — The interface must be used as is URL: "
                f"{DCD_URL}?month=202608&rank_data_type=11&count=100&offset=0 (Rewriting of the path is strictly prohibited)",
                "The request must carry User-Agent and Referer request headers",
            ],
            parameters=[
                {"name": "brand_name", "type": "string", "description": "Brand name", "required": True},
                {"name": "month", "type": "string", "description": "month", "required": True},
            ],
            test_input={"brand_name": "BYD", "month": "202609"},
        )
        probe = build_interface_probe(spec)
        assert probe is not None
        # baseline = Documented query parameters + test_input Override of document parameter (month with new value)
        assert probe["baseline_params"] == {
            "month": "202609", "rank_data_type": "11", "count": "100", "offset": "0",
        }
        # brand_name not in documented query parameters → Suspected business filtering parameters
        assert probe["suspected_filters"] == ["brand_name"]
        # The test_input passed to the sandbox remains unchanged (the runner is called by tool_id)
        assert probe["params"] == {"brand_name": "BYD", "month": "202609"}
        # Probe code contains differential test logic
        assert "ignored_params" in probe["code"]
        assert "filter_effective_params" in probe["code"]

    def test_documented_params_from_dedicated_constraint(self):
        """Real link format: URL contract only contains base address + Special query parameter constraints → Differential still triggers.

        In the requirements analysis stage, the URL contract constraints are stripped of the query string (to prevent hard-coded example parameters),
        The query string uses interface query parameters (user URL original query string) to constrain a single column.
        """
        spec = _make_spec(
            constraints=[
                " [Interface specifications — The interface must be used as is URL: "
                f"{DCD_URL} (From user needs, the path/parameter name is strictly prohibited to be rewritten, for example, rank_data must not be written as rank/data)",
                " [Interface specifications] Interface query parameters (user URL original query string): "
                "month=202608&rank_data_type=11&count=100&offset=0"
                "——Only these parameters are the real query parameters of the interface and can be assembled into URL requests;"
                "The remaining business filtering conditions must be filtered locally according to the return field after pulling the data.",
                "The request must carry User-Agent and Referer request headers",
            ],
            parameters=[
                {"name": "brand_name", "type": "string", "description": "Brand name", "required": True},
                {"name": "month", "type": "string", "description": "month", "required": True},
            ],
            test_input={"brand_name": "BYD", "month": "202609"},
        )
        probe = build_interface_probe(spec)
        assert probe is not None
        assert probe["url"] == DCD_URL
        assert probe["baseline_params"] == {
            "month": "202609", "rank_data_type": "11", "count": "100", "offset": "0",
        }
        assert probe["suspected_filters"] == ["brand_name"]

    def test_no_query_url_all_params_as_baseline(self):
        """URL Without query string: there is no way to distinguish document/business parameters, all are used as baselines (no difference is made)"""
        spec = _make_spec(
            parameters=[
                {"name": "brand_name", "type": "string", "description": "Brand name", "required": True},
                {"name": "month", "type": "string", "description": "month", "required": True},
            ],
            test_input={"brand_name": "BYD", "month": "202608"},
        )
        probe = build_interface_probe(spec)
        assert probe is not None
        assert probe["baseline_params"] == {"brand_name": "BYD", "month": "202608"}
        assert probe["suspected_filters"] == []


class TestInterpretProbeResult:
    def _sandbox(self, output=None, success=True, error=None):
        return SandboxResult(success=success, error=error, output=output)

    def test_verified_with_data(self):
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": True, "data_items": 100,
            "first_item_keys": ["rank", "series_name"],
        }))
        assert result["status"] == "verified"
        assert result["data_items"] == 100
        assert result["sample_fields"] == ["rank", "series_name"]

    def test_failed_on_404(self):
        result = interpret_probe_result(self._sandbox(output={"http_status": 404}))
        assert result["status"] == "failed"
        assert "404" in result["message"]

    def test_failed_on_network_error(self):
        result = interpret_probe_result(self._sandbox(output={
            "error": "ConnectionError: Connection timeout"
        }))
        assert result["status"] == "failed"
        assert "Not reachable" in result["message"]

    def test_failed_on_sandbox_error(self):
        result = interpret_probe_result(self._sandbox(success=False, error="timeout"))
        assert result["status"] == "failed"

    def test_warning_on_200_no_data(self):
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": True,
        }))
        assert result["status"] == "warning"

    def test_warning_on_non_json(self):
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": False, "body_head": "<html>",
        }))
        assert result["status"] == "warning"

    def test_ignored_params_reported_with_local_filter_hint(self):
        """Differential testing: Parameter ignored by interface → verdict Mark ignored_params and prompt for local filtering"""
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": True, "data_items": 100,
            "first_item_keys": ["rank", "series_name"],
            "ignored_params": ["brand_name"],
            "filter_test": {"tested": ["brand_name"], "baseline_items": 100,
                            "with_filter_items": 100, "with_filter_status": 200},
        }))
        assert result["status"] == "verified"
        assert result["ignored_params"] == ["brand_name"]
        assert "Ignored by interface" in result["message"]
        assert "local" in result["message"]

    def test_effective_filter_params_reported(self):
        """Differential testing: parameter change return → verdict mark server_filter_params"""
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": True, "data_items": 100,
            "first_item_keys": ["rank", "series_name"],
            "filter_effective_params": ["brand_name"],
        }))
        assert result["status"] == "verified"
        assert result["server_filter_params"] == ["brand_name"]
        assert "Server side filtering" in result["message"]

    def test_no_differential_output_unchanged(self):
        """No differential field: verdict without ignored_params / server_filter_params"""
        result = interpret_probe_result(self._sandbox(output={
            "http_status": 200, "json_ok": True, "data_items": 100,
            "first_item_keys": ["rank"],
        }))
        assert "ignored_params" not in result
        assert "server_filter_params" not in result


# ---------- Upgrade scenario: parent code query parameter extraction ----------

_PARENT_CODE = '''
import requests

RANK_URL = "https://www.dongchedi.com/motor/pc/car/rank_data"


def _get_page(month, offset):
    params = {
        "month": month,
        "rank_data_type": "11",
        "count": "100",
        "offset": str(offset),
    }
    return requests.get(RANK_URL, params=params, timeout=10).json()
'''


class TestParentCodeParamExtraction:
    def test_extract_params_with_static_values(self):
        """AST Extract params key and static value: literal has value, runtime variable is None (don t guess the default)"""
        params = _extract_query_params_from_parent_code(_PARENT_CODE)
        assert list(params.keys()) == ["month", "rank_data_type", "count", "offset"]
        assert params["rank_data_type"] == "11"   # literal
        assert params["count"] == "100"           # literal
        assert params["month"] is None            # Function input parameters, unknown during runtime
        assert params["offset"] is None           # str(Add ginseng), Runtime unknown

    def test_only_params_flow_collected_not_other_dicts(self):
        """Regression (real bug): only collect incoming requests(params=) dictionary.

        Request header dictionary, brand alias mapping, output result dictionary and params dictionary in the parent code
        When keys with the same name coexist, they must not be mixed into the query parameter baseline (it was once User-Agent/Referer/
        Alias/output fields are all blended into the preflight baseline).
        """
        code = (
            "import requests\n"
            "URL = 'https://x.com/api'\n"
            "HEADERS = {'User-Agent': 'ua', 'Referer': 'https://x.com/'}\n"
            "ALIASES = {'aito Ask the world': 'Ask the world', 'aito': 'Ask the world'}\n"
            "PAGE_SIZE = 100\n"
            "\n"
            "def fetch(month):\n"
            "    params = {'month': month, 'count': str(PAGE_SIZE), 'offset': '0'}\n"
            "    resp = requests.get(URL, params=params, headers=HEADERS)\n"
            "    result = {'month': month, 'offset': 0, 'pages_fetched': 1, 'fetch_mode': 'single_page'}\n"
            "    return result\n"
        )
        params = _extract_query_params_from_parent_code(code)
        # Only real incoming params= dictionary
        assert set(params.keys()) == {"month", "count", "offset"}
        assert params["count"] == "100"   # constant tracking
        assert params["offset"] == "0"    # literal
        assert params["month"] is None    # runtime variables
        # Header/alias/output dictionary keys never appear
        assert "User-Agent" not in params
        assert "Referer" not in params
        assert "aito" not in params
        assert "fetch_mode" not in params
        assert "pages_fetched" not in params

    def test_constant_tracking(self):
        """module constants (PAGE_SIZE = 100) trace to params value"""
        code = (
            "import requests\n"
            "PAGE_SIZE = 100\n"
            "params = {'month': '202608', 'count': str(PAGE_SIZE)}\n"
            "requests.get('https://x.com/api', params=params)\n"
        )
        params = _extract_query_params_from_parent_code(code)
        assert params == {"month": "202608", "count": "100"}

    def test_inline_params_dict_supported(self):
        """inline params={...} The writing method can also extract keys and literal values."""
        code = (
            "import requests\n"
            "requests.get('https://x.com/api', params={'page': 1, 'size': 20})\n"
        )
        assert _extract_query_params_from_parent_code(code) == {"page": 1, "size": 20}

    def test_invalid_code_returns_empty(self):
        assert _extract_query_params_from_parent_code("def (") == {}

    def test_upgrade_baseline_uses_parent_static_values(self):
        """Upgrade scenario: The baseline uses the static value of the parent code, the new spec parameter is differentiated, and parameters without static value are not hard-coded.

        - month/rank_data_type: spec There are parameters with the same name → spec value first
        - count: parent code literal "100" → Enter the baseline
        - offset: The parent code is a runtime variable and spec has no parameter with the same name. → Not sent (don t hard-code the default value)
        - brand/limit: not in parent code parameter → Differential testing
        """
        spec = _make_spec(
            parameters=[
                {"name": "month", "type": "string", "description": "month", "required": True},
                {"name": "rank_data_type", "type": "string", "description": "List type", "required": False},
                {"name": "brand", "type": "string", "description": "brand", "required": False},
                {"name": "limit", "type": "integer", "description": "Upper limit of number of articles", "required": False},
            ],
            test_input={"month": "202608", "rank_data_type": "sale", "brand": "BYD", "limit": 10},
        )
        probe = build_interface_probe(spec, parent_code=_PARENT_CODE)
        assert probe is not None
        assert probe["baseline_params"]["month"] == "202608"
        assert probe["baseline_params"]["rank_data_type"] == "sale"
        assert probe["baseline_params"]["count"] == "100"
        # Unable to find static value → Do not hard-code the default and do not send this parameter.
        assert "offset" not in probe["baseline_params"]
        # The business parameters of the new spec are differentiated (no longer regarded as available interface parameters)
        assert set(probe["suspected_filters"]) == {"brand", "limit"}

    def test_without_parent_code_no_diff_when_bare_url(self):
        """Regression: When there is no parent code and no query string in the constraint, all parameters are used as baseline (no difference is performed)"""
        spec = _make_spec(
            parameters=[{"name": "brand", "type": "string", "description": "brand", "required": False}],
            test_input={"brand": "BYD"},
        )
        probe = build_interface_probe(spec)
        assert probe is not None
        assert probe["suspected_filters"] == []
