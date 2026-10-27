# -*- coding: utf-8 -*-
"""External interface preflight — Connectivity verification during specification validation phase + Query parameter differential testing.

Background: External interface integration (data sources outside the directory) cannot verify whether the interface specifications are available before code generation.
Interface address/request header errors are not exposed until the sandbox execution phase (2-4 minutes per round of code generation),
A lot of iteration time is wasted. Preflight uses the sandbox to actually call the interface once when confirming specifications.
 [ Interface Unreachable/404/Parameter Error goes to the confirmation page in advance.

Differential testing: The interface usually ignores unknown query parameters (still returns 200 + full data),
 [HTTP 200] It does not prove that this parameter has filtering semantics. Preflight pair spec is not in user URL
Make differential calls for parameters in the query string (such as brand_name):
- Both responses have the same signature → This parameter is ignored by the interface → The code must be filtered locally after pulling the full amount
- Signature changes → This parameter is suspected of server-side filtering taking effect. → Available as URL query parameters

Usage (service layer):
    probe = build_interface_probe(spec)          # Extract URL construction detection code from spec.constraints
    sandbox = SandboxRunner().run(probe.code, spec, test_input=probe.params)
    verdict = interpret_probe_result(sandbox)    # verified / warning / failed + news
"""

import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl

# ASCII URL Character set (consistent with static_validator interface URL verification:
# Chinese characters are truncated when they are close to the URL to avoid using text such as "rank_data initiated" as a URL)
_URL_RE = re.compile(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _find_interface_urls(spec: Any) -> List[str]:
    """Extract all URLs in constraints that match the original text (including query string, in order of appearance)"""
    constraint_text = "\n".join(str(c) for c in (getattr(spec, "constraints", None) or []))
    return [m.group(0) for m in _URL_RE.finditer(constraint_text)]


def _is_api_url(url: str) -> bool:
    """At least 1 level path after the domain name, excluding pure domain name references (such as Referer root domain name)"""
    return len([s for s in url.split("//", 1)[-1].split("/") if s]) >= 2


def _extract_interface_url(spec: Any) -> Optional[str]:
    """Extract the interface URL from spec.constraints (constraint lines containing URLs, take the first one; exclude pure domain names)"""
    for raw in _find_interface_urls(spec):
        url = raw.split("?")[0].rstrip(".,;:")
        if _is_api_url(url):
            return url
    return None


def _extract_documented_params(spec: Any) -> Dict[str, str]:
    """Extract documented query parameters——The basis for distinguishing the real parameters of the interface from the business filtering parameters.

    Two sources (in order of priority):
    1.  [Interface specifications] Interface query parameters (user URL original query string) constraints——requirements analysis stage
       Extract writes from user sessions (URL contract constraints only keep base address, query string single column)
    2. constraints Complete URL with query string (original URL written directly by LLM)
    """
    constraint_text = "\n".join(str(c) for c in (getattr(spec, "constraints", None) or []))
    # Source 1: Specially documented query parameter constraints
    m = re.search(
        r"Interface query parameters (user URL original query string)[:: ]\s*([A-Za-z0-9\-._~%&=]+)", constraint_text
    )
    if m:
        try:
            pairs = parse_qsl(m.group(1), keep_blank_values=True)
        except Exception:
            pairs = []
        if pairs:
            return dict(pairs)
    # Source 2: Complete query string in constraints URL
    for raw in _find_interface_urls(spec):
        if "?" not in raw:
            continue
        url = raw.split("?")[0].rstrip(".,;:")
        if not _is_api_url(url):
            continue
        query = raw.split("?", 1)[1].rstrip(".,;:")
        try:
            pairs = parse_qsl(query, keep_blank_values=True)
        except Exception:
            continue
        if pairs:
            return dict(pairs)
    return {}


def _static_eval(node: Any, constants: Dict[str, Any]) -> Any:
    """Minimize static evaluation of the AST expression, and return None if no result is found.

    Support: literals, module/local constant names (PAGE_SIZE = 100) , str(x) Single layer packaging.
    Function parameters (runtime variables such as month/offset) are always returned None——Don t guess the default value.
    """
    import ast

    if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool)):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.Call):
        # Only supports str(x)/int(x) This type of single-layer literal packaging
        if isinstance(node.func, ast.Name) and node.func.id in ("str", "int", "float"):
            if len(node.args) == 1:
                inner = _static_eval(node.args[0], constants)
                if inner is None:
                    return None
                try:
                    return {"str": str, "int": int, "float": float}[node.func.id](inner)
                except (ValueError, TypeError):
                    return None
    return None


def _extract_query_params_from_parent_code(code: str) -> Dict[str, Any]:
    """Extract the actual query parameters used by the requests request and their static values (AST) from the parent version code.

    Upgrade scenario: The interface query parameter constraint is the bare URL (no query string) extracted from the parent code,
    Documented parameter source is empty. The parent code is a multi-round verified implementation whose requests call
    params The key in is the real query parameter of the interface——Only with this as the baseline can the new spec
    The fictitious business parameters are correctly included in the differential test.

    Only collect real inflows `params=` dictionary (inline dictionary / assigned to a variable and then passed in
    params dictionary). Request header dictionary, alias mapping table, and output results in the parent code
    Dictionaries, etc. are all excluded.——Because he collected all dictionary assignments, he User-Agent/Referer/
    Brand aliases/output fields are all blended into the preflight baseline.

    The value sources are all objective facts in the code (literal/constant assignment) and do not maintain any
    Parameter name→Hard-coded mapping of default values; runtime variables (function input parameters) evaluate to None,
    The caller accordingly skips this parameter (HTTP query parameters are usually optional, and the server has default behavior).

    Returns:
        orderly {Parameter name: static value or None}
    """
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {}

    ordered: Dict[str, Any] = {}

    def _collect(dict_node: ast.Dict) -> None:
        for k, v in zip(dict_node.keys, dict_node.values):
            if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value not in ordered:
                # Static evaluation of values is deferred (the constant table is most complete after all nodes have been collected)
                ordered[k.value] = v

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in getattr(node, "keywords", None) or []:
            if kw.arg != "params":
                continue
            # inline params={...}
            if isinstance(kw.value, ast.Dict):
                _collect(kw.value)
            # params=p (p is a variable)→ collect p = {...} assignment dictionary
            elif isinstance(kw.value, ast.Name):
                for sub in ast.walk(tree):
                    if (
                        isinstance(sub, ast.Assign)
                        and isinstance(sub.value, ast.Dict)
                        and any(
                            isinstance(t, ast.Name) and t.id == kw.value.id
                            for t in sub.targets
                        )
                    ):
                        _collect(sub.value)

    # Pass 2: Constant table (PAGE_SIZE = 100 etc.), for static evaluation
    constants: Dict[str, Any] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            val = _static_eval(node.value, constants)
            if val is not None:
                constants[node.targets[0].id] = val

    return {k: _static_eval(v, constants) for k, v in ordered.items()}


def build_interface_probe(spec: Any, parent_code: str = "") -> Optional[Dict[str, Any]]:
    """Construct interface preflight detection code.

    Returns:
        {"code": Detect function code (function name = spec.tool_id, **kwargs signature),
         "params": Request parameters passed to the sandbox (spec.test_input first, followed by parameter default values),
         "url": Probe interface address,
         "baseline_params": Baseline request parameters (documented query parameters + test_input its coverage),
         "suspected_filters": Suspected business filtering parameter name (not included in documented query parameters, do differential testing)}
        Returns None if there is no interface URL (non-external interface requirement/constraint is missing).
    """
    url = _extract_interface_url(spec)
    if not url:
        return None

    # Referer: When the constraint text explicitly requires it, the interface origin root path is used by default.
    constraint_text = "\n".join(str(c) for c in (getattr(spec, "constraints", None) or []))
    origin = url.split("//", 1)[0] + "//" + url.split("//", 1)[-1].split("/", 1)[0] + "/"
    headers = {"User-Agent": _DEFAULT_UA}
    if "Referer" in constraint_text or "referer" in constraint_text:
        headers["Referer"] = origin

    # Request parameters: test_input first, followed by default parameter values
    params: Dict[str, Any] = dict(getattr(spec, "test_input", None) or {})
    if not params:
        for p in getattr(spec, "parameters", None) or []:
            default = getattr(p, "default", None)
            if default is not None:
                params[getattr(p, "name", "")] = default

    # Differential test grouping: documented query parameters are the baseline; parameters in the spec that are not in the documented query
    #  (Usually the parameters created by demand analysis for business filtering, such as brand_name) are used for differential verification.
    documented = _extract_documented_params(spec)
    # Upgrade scenario: When the constraints only contain the bare URL extracted from the parent code (no query string),
    # Extract the query parameters actually used by its requests from the parent version code AST as documented parameters
    if not documented and parent_code:
        documented = _extract_query_params_from_parent_code(parent_code)

    if documented:
        baseline = {}
        for k, doc_v in documented.items():
            if k in params and params[k] not in (None, ""):
                # spec Parameter values with the same name take precedence (test_input/default value/parent code static value)
                baseline[k] = params[k]
            elif doc_v not in (None, ""):
                # Static evaluable source: URL query string example value / parent code literal or constant
                baseline[k] = doc_v
            # The static value (runtime variable) cannot be found and spec has no parameter with the same name. → Do not send this parameter,
            # Do not hard-code default values: HTTP query parameters are usually optional, and the server has default behavior;
            # If this parameter is required, the preflight will truthfully return a failure instead of relying on guesswork to get through.
        suspected = {k: v for k, v in params.items() if k not in documented}
    else:
        # The user URL does not contain a query string: there is no way to distinguish between document parameters and business parameters, all of which are used as baselines (no difference is made)
        baseline = dict(params)
        suspected = {}

    func_name = getattr(spec, "tool_id", "interface_probe")
    code = f'''def {func_name}(**kwargs):
    """Interface pre-check (automatically generated detection code): Really call the external interface to verify connectivity and parameter semantics"""
    import requests

    url = {url!r}
    headers = {headers!r}
    baseline = {baseline!r}
    filter_values = {suspected!r}

    def _call(p):
        try:
            resp = requests.get(url, params=p, headers=headers, timeout=10)
            out = {{"http_status": resp.status_code,
                    "content_type": resp.headers.get("content-type", "")}}
            body = resp.text or ""
            out["body_head"] = body[:300]
            try:
                data = resp.json()
                out["json_ok"] = True
                if isinstance(data, dict):
                    out["json_keys"] = [str(k) for k in list(data.keys())[:12]]
                    inner = data.get("data")
                    if isinstance(inner, dict):
                        for key in ("list", "items", "rows", "data"):
                            v = inner.get(key)
                            if isinstance(v, list):
                                out["data_items"] = len(v)
                                if v and isinstance(v[0], dict):
                                    out["first_item_keys"] = [str(k) for k in list(v[0].keys())[:15]]
                                break
                    elif isinstance(inner, list):
                        out["data_items"] = len(inner)
                elif isinstance(data, list):
                    out["data_items"] = len(data)
            except Exception:
                out["json_ok"] = False
            return out
        except Exception as exc:
            return {{"error": type(exc).__name__ + ": " + str(exc)}}

    overrides = dict(kwargs or {{}})
    base_params = dict(baseline)
    for k, v in overrides.items():
        if k not in filter_values:
            base_params[k] = v
    base_out = _call(base_params)

    result = {{"probe": True,
               "http_status": base_out.get("http_status"),
               "content_type": base_out.get("content_type"),
               "body_head": base_out.get("body_head"),
               "json_ok": base_out.get("json_ok", False),
               "json_keys": base_out.get("json_keys"),
               "data_items": base_out.get("data_items"),
               "first_item_keys": base_out.get("first_item_keys")}}
    if base_out.get("error"):
        result["error"] = base_out["error"]
        return result

    # Differential Testing: Baseline vs. Baseline+Suspected filter parameters, compare response signatures.
    # The signature only uses structurally stable items (status code/number of items/field names) and does not compare data values.——
    # The values of real-time data such as rankings naturally fluctuate between calls. Comparing values will misjudge ignored as filtering effective 
    if filter_values and base_out.get("http_status") == 200 and base_out.get("data_items"):
        full_params = dict(base_params)
        for k, v in filter_values.items():
            full_params[k] = overrides.get(k, v)
        full_out = _call(full_params)
        sig_b = (base_out.get("http_status"), base_out.get("data_items"),
                 tuple(base_out.get("first_item_keys") or []))
        sig_f = (full_out.get("http_status"), full_out.get("data_items"),
                 tuple(full_out.get("first_item_keys") or []))
        tested = sorted(filter_values.keys())
        if sig_b == sig_f:
            result["ignored_params"] = tested
        else:
            result["filter_effective_params"] = tested
        result["filter_test"] = {{
            "tested": tested,
            "baseline_items": base_out.get("data_items"),
            "with_filter_items": full_out.get("data_items"),
            "with_filter_status": full_out.get("http_status"),
        }}
    return result
'''
    return {
        "code": code,
        "params": params,
        "url": url,
        "baseline_params": baseline,
        "suspected_filters": sorted(suspected.keys()),
    }


def build_preflight_facts_text(preflight: Any) -> str:
    """Render the preflight conclusion as LLM-oriented [Interface Measured Facts] block text.

    Provides two injections at the same time:
    - CodeGenerator user prompt (pipeline_tool Internal code generation per round)
    - Agent Loop Coordinator task prompt (the coordinator writes feedback accordingly and will not give
       [Error guidance such as Plug business filtering parameters into the URL )
    If there is no preflight result, an empty string is returned.
    """
    if not isinstance(preflight, dict) or not preflight.get("url"):
        return ""

    lines = [
        " [🔍 The actual test facts of the interface (the interface has been actually called during the pre-checking stage for verification)]",
        f"- 实测 URL: {preflight.get('url')}",
    ]
    http_status = preflight.get("http_status")
    if http_status is not None:
        lines.append(f"- HTTP 状态: {http_status}")

    sample_fields = preflight.get("sample_fields") or []
    data_items = preflight.get("data_items")
    if preflight.get("status") == "verified":
        if data_items is not None:
            lines.append(f"- 实测返回数据条数: {data_items}")
        if sample_fields:
            lines.append(
                "- Returns the real fields of the entry (this shall prevail, fabrication is strictly prohibited): "
                + ", ".join(str(f) for f in sample_fields)
            )
        probed_params = preflight.get("probed_params") or {}
        if probed_params:
            params_desc = ", ".join(
                f"{k}={v!r}" for k, v in list(probed_params.items())[:10]
            )
            lines.append(f"- Actual testing verifies the available query parameters (already spelled into the URL and the request is successful): {params_desc}")
        ignored_params = [str(p) for p in (preflight.get("ignored_params") or []) if p]
        if ignored_params:
            lines.append(
                "- ⚠️ The following parameters have been measured and ignored by the interface (the exact same data is returned whether passed in or not): "
                + "、".join(ignored_params)
            )
        # Data boundary determination (data-driven, no hard-coded keywords): For each ignored business filtering parameter,
        # Check whether there are semantically corresponding fields in the returned fields (tokens include each other).
        # Doesn't match → This filtering concept has no bearing fields in the interface data, and the data boundaries must be declared.——
        # Historical lesson: LLM created all 404s for new endpoints to complete the mapping, wasting the entire iteration.
        # The parameter names and field names all come from actual measurements. If you change another data source/change a business, it will still be valid.
        unmatched_filters: List[str] = []
        for p in ignored_params:
            token = str(p).lower()
            if not any(token in str(f).lower() or str(f).lower() in token
                       for f in sample_fields):
                unmatched_filters.append(str(p))
        if unmatched_filters:
            lines.append(
                f"- ⚠️ The actual measured return field does not exist with {', '.join(unmatched_filters)} Corresponding fields"
                " (There are no name-related fields in the field list): Filtering based on this condition can only rely on returning the"
                "The name field is approximate matched and may not be completely covered; if it cannot be completely covered, it must be included in the output."
                "It is clearly stated that the interface data does not contain relevant fields, and the results may be incomplete. It is strictly forbidden to create new interface endpoints."
            )
        server_filters = [str(p) for p in (preflight.get("server_filter_params") or []) if p]
        if server_filters:
            lines.append(
                "- The actual measurement of the following business parameters will change the interface return (server-side filtering is suspected to be effective and can be used as URL query parameters): "
                + "、".join(server_filters)
            )
        lines += [
            "",
            "Measured constraints (must be adhered to):",
            "- The interface return fields referenced in the code must come from the measured real field list above, and fabricated field names are strictly prohibited.",
            "- Query parameters are only allowed to use query parameters that are available through actual testing and verification and parameters that are clearly required by specifications.",
        ]
        if ignored_params:
            lines.append(
                f"- {', '.join(ignored_params)} It has been measured that it is ignored by the interface."
                "It is strictly prohibited to spell in the URL; the corresponding business filtering must first pull the interface data"
                " (If necessary, use actual testing to verify the available query parameters (all available query parameters), and then press the return field to implement it locally."
            )
        else:
            lines.append(
                "- It is strictly prohibited to fabricate business filtering conditions as interface query parameters and spell them into the URL;"
                "If the filtering/sorting/aggregation required for business is not in the measured query parameters, the interface data must be pulled first."
                " (If necessary, use actual testing to verify the available query parameters (all available query parameters), and then use the return field to implement it locally."
            )
    else:
        # warning: The interface is reachable but no data entry is recognized or it is not JSON and the structure is not discovered.
        lines += [
            f"- 预检结论: {preflight.get('message') or '接口可达但数据结构未探明'}",
            "",
            "Measured constraints (must be adhered to):",
            "- The interface is reachable but the data structure is not known: when parsing the response, first get the JSON top-level key positioning data list,"
            "It is strictly prohibited to make up field names or data structures based on training memory.",
            "- It is strictly prohibited to fabricate business filtering conditions as interface query parameters and spell them into the URL;"
            "This type of filtering must be implemented locally using the return field after pulling the data.",
        ]
    return "\n".join(lines) + "\n"


def interpret_probe_result(sandbox_result: Any) -> Dict[str, Any]:
    """Interpret the sandbox execution results as preflight conclusions.

    Returns:
        {"status": "verified" | "warning" | "failed", "message": show message, ...Details}
        Differential test output: ignored_params (ignored by the interface and must be filtered locally)/
        server_filter_params (It is suspected that server-side filtering has taken effect, you can spell the URL)
    """
    if not getattr(sandbox_result, "success", False):
        return {
            "status": "failed",
            "message": f"预检脚本执行失败: {getattr(sandbox_result, 'error', None) or '未知错误'}",
        }
    output = getattr(sandbox_result, "output", None)
    if not isinstance(output, dict):
        return {"status": "failed", "message": "预检未返回结构化结果"}

    if output.get("error"):
        return {"status": "failed", "message": f"接口不可达: {output['error']}"}

    status_code = output.get("http_status")
    if status_code != 200:
        hints = {
            404: "Interface path does not exist (404)——Please check URL path spelling",
            403: "Interface access denied (403)——May require additional request headers or authentication",
            401: "Interface requires authentication (401)——Please add authentication method",
            429: "Interface current limit (429)——Try again later or call less frequently",
        }
        hint = hints.get(status_code, f"接口返回异常状态码 {status_code}")
        return {"status": "failed", "http_status": status_code, "message": hint}

    data_items = output.get("data_items")
    if data_items:
        verdict = {
            "status": "verified",
            "http_status": 200,
            "data_items": data_items,
            "sample_fields": (output.get("first_item_keys") or [])[:8],
            "message": f"接口连通性已验证：HTTP 200，返回 {data_items} 条数据",
        }
    elif output.get("json_ok"):
        verdict = {
            "status": "warning",
            "http_status": 200,
            "message": "Interface reachable (HTTP 200, JSON response), but no data entry recognized——It may be a semantic problem with the query parameters. It is recommended to check the parameters.",
        }
    else:
        verdict = {
            "status": "warning",
            "http_status": 200,
            "message": "The interface is reachable (HTTP 200), but non-JSON content is returned——The web page may be blocked by anti-crawling. Please check the request header requirements.",
        }

    # Differential test conclusion (will be output only when the baseline has data)
    ignored = [str(p) for p in (output.get("ignored_params") or []) if p]
    if ignored:
        verdict["ignored_params"] = ignored
        verdict["message"] += (
            f"; Actual measurement {(', '.join(ignored))} Parameters are ignored by the interface (do not affect return),"
            "Corresponding filtering needs to be implemented locally in the code"
        )
    effective = [str(p) for p in (output.get("filter_effective_params") or []) if p]
    if effective:
        verdict["server_filter_params"] = effective
        verdict["message"] += f"; Actual measurement {(', '.join(effective))} The parameters will change the interface return (server-side filtering is suspected to be effective)"
    return verdict
