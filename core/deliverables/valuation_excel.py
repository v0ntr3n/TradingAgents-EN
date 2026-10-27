"""Valuation Calculation Excel Deliverables (A10-D1)

Declarative optional deliverables: The intelligent assistant layer is scheduled according to user declarations, with zero changes to the fixed analysis process.

The deterministic layer in the three-tier architecture:
- render_valuation_excel: Model specifications JSON → .xlsx (true formula + Assuming input grid)
- validate_valuation_excel: Reopen the file and verify the existence of the formula/input consistency/self-consistent calculation

Alignment of specification contracts and validation rules docs/05-design/v4.0/financial-schema-examples/
（output_contract / verifier_rule / applicability_rule），
For the design documentation, see docs/05-design/v3.0/valuation-excel-deliverable-design.md.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

# ==================== constant ====================

SHEET_EARNINGS = "Profit deduction"
SHEET_VALUATION = "Valuation scenario"

SUPPORTED_METHODS = ("PE",)  # PB/PEG The net assets per share/growth rate formula is required and will be available after the v4.0 Schema is released.

# Assume input grid style (light yellow background, prompt can be edited)
_INPUT_FILL = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid")
_HEADER_FILL = PatternFill(start_color="D9E2F3", end_color="D9E2F3", fill_type="solid")
_BOLD = Font(bold=True)
_CENTER = Alignment(horizontal="center")

_EPS_TOL = 1e-9


class ValuationSpecError(ValueError):
    """The model specifications are illegal (blocking rendering)"""


# ==================== Specification verification ====================

def _forecast_net_profit(spec: dict, period: str) -> Optional[float]:
    """Calculate the net profit (100 million yuan) during a certain forecast period. There is no return during the period. None"""
    prev_rev: Optional[float] = None
    for h in spec["earnings_forecast"]["history"]:
        if h["period"] == period:
            return float(h["net_profit"])
        prev_rev = float(h["revenue"])
    for a in spec["earnings_forecast"]["assumptions"]:
        rev = (prev_rev or 0.0) * (1 + float(a["revenue_growth"]))
        margin = float(a["net_margin"])
        if a["period"] == period:
            return rev * margin
        prev_rev = rev
    return None


def validate_spec(spec: Dict[str, Any]) -> List[str]:
    """Verify model specifications and return an error list (empty list = passed)

    Rule alignment v4.0 verifier_rule:
    - Required fields (output_contract.required_fields)
    - Method applicability (applicability_rule: PE requires positive profit)
    - Assume non-trivial (missing or zero-blocking)
    """
    errors: List[str] = []

    def _need(obj: dict, key: str, ctx: str):
        if key not in obj or obj[key] in (None, ""):
            errors.append(f"{ctx}Missing field {key}")

    # ---- Top level required ----
    for key in ("ticker", "stock_name", "analysis_date", "share_count",
                "current_price", "earnings_forecast", "valuation"):
        _need(spec, key, "Specifications")
    if errors:
        return errors

    if float(spec["share_count"]) <= 0:
        errors.append("Total share capital must be a positive number")
    if float(spec["current_price"]) <= 0:
        errors.append("The current price must be a positive number")

    # ---- Profit deduction ----
    ef = spec["earnings_forecast"]
    history = ef.get("history") or []
    assumptions = ef.get("assumptions") or []
    if not history:
        errors.append("Profit deduction lacks historical data (history is empty)")
    if not assumptions:
        errors.append("Profit deduction is missing forecast assumptions (assumptions is empty)")

    periods = []
    for i, h in enumerate(history):
        ctx = f"Historical data no. {i + 1} OK"
        _need(h, "period", ctx)
        _need(h, "revenue", ctx)
        _need(h, "net_profit", ctx)
        if errors:
            return errors
        periods.append(h["period"])
        if float(h["revenue"]) <= 0:
            errors.append(f"{ctx}Revenue must be positive")

    for i, a in enumerate(assumptions):
        ctx = f"Forecast assumptions {a.get('period', f'No. {i + 1} OK')}"
        _need(a, "period", ctx)
        _need(a, "revenue_growth", ctx)
        _need(a, "net_margin", ctx)
        if errors:
            return errors
        periods.append(a["period"])
        growth, margin = float(a["revenue_growth"]), float(a["net_margin"])
        if growth == 0:
            errors.append(f"{ctx}Revenue growth is zero (assuming non-trivial rules)")
        if margin == 0:
            errors.append(f"{ctx}Net interest rate is zero (assuming non-trivial rules)")
        if margin < 0 or margin > 1:
            errors.append(f"{ctx}The net interest rate should be (0, 1] interval, current {margin}")
        if growth <= -1:
            errors.append(f"{ctx}Revenue growth cannot <= -100%")

    if len(set(periods)) != len(periods):
        errors.append("There is duplication in the period (the period of history and assumptions must be unique)")

    # ---- Valuation scenario ----
    val = spec["valuation"]
    scenarios = val.get("scenarios") or []
    if not scenarios:
        errors.append("Valuation scenarios are empty (at least one scenario)")

    for i, s in enumerate(scenarios):
        ctx = f"Valuation Scenario {s.get('name', f'No. {i + 1} OK')}] "
        _need(s, "name", ctx)
        _need(s, "method", ctx)
        _need(s, "multiple", ctx)
        _need(s, "eps_period", ctx)
        _need(s, "benchmark_basis", ctx)
        if errors:
            return errors
        method = str(s["method"]).upper()
        if method not in SUPPORTED_METHODS:
            errors.append(f"{ctx}method {method} Not supported (Supported {SUPPORTED_METHODS}) ")
        multiple = float(s["multiple"])
        if multiple == 0:
            errors.append(f"{ctx}The multiple is zero (assuming non-trivial rules)")
        if multiple < 0:
            errors.append(f"{ctx}The multiple must be a positive number")
        # Applicability: PE requires that the net profit in the base period be positive (rule.pe_requires_positive_earnings)
        if method == "PE":
            profit = _forecast_net_profit(spec, s["eps_period"])
            if profit is None:
                errors.append(f"{ctx}EPS base period {s['eps_period']} Not in profit deduction")
            elif profit <= 0:
                errors.append(
                    f"{ctx}base period {s['eps_period']} Net profit attributable to parent company is {profit:.1f} Billion yuan (not positive),"
                    f"The applicable conditions for PE are not met (positive profit); in the loss scenario, please use the profit period as the benchmark, or reduce the weight of the scenario"
                )
        elif s["eps_period"] not in periods:
            errors.append(f"{ctx}EPS base period {s['eps_period']} Not in profit deduction")

    return errors


# ==================== rendering ====================

def _style_header(ws, row: int, cols: int) -> None:
    for c in range(1, cols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = _BOLD
        cell.fill = _HEADER_FILL
        cell.alignment = _CENTER


def _render_earnings_sheet(ws, spec: dict) -> Dict[str, int]:
    """Render profit deduction Sheet and return {period: Line number}"""
    ef = spec["earnings_forecast"]
    ws.title = SHEET_EARNINGS
    ws["A1"] = f"Profit deduction — {spec['stock_name']} ({spec['ticker']}) "
    ws["A1"].font = Font(bold=True, size=13)

    headers = ["period", "Revenue (100 million yuan)", "revenue growth", "net profit margin", "Net profit attributable to parent company (100 million yuan)", "Assumption basis"]
    for c, h in enumerate(headers, start=1):
        ws.cell(row=3, column=c, value=h)
    _style_header(ws, 3, len(headers))

    period_row: Dict[str, int] = {}
    r = 4
    for h in ef["history"]:
        ws.cell(row=r, column=1, value=h["period"])
        ws.cell(row=r, column=2, value=float(h["revenue"])).number_format = "#,##0.0"
        # Historical line: Growth rate/net interest rate also uses the formula to ensure auditability
        if r == 4:
            ws.cell(row=r, column=3, value="—").alignment = _CENTER
        else:
            ws.cell(row=r, column=3, value=f"=B{r}/B{r - 1}-1").number_format = "0.0%"
        ws.cell(row=r, column=4, value=f"=E{r}/B{r}").number_format = "0.0%"
        ws.cell(row=r, column=5, value=float(h["net_profit"])).number_format = "#,##0.0"
        ws.cell(row=r, column=6, value="Actual value (financial reporting caliber)")
        period_row[h["period"]] = r
        r += 1

    for a in ef["assumptions"]:
        ws.cell(row=r, column=1, value=a["period"])
        # Forecast row: revenue = Last issue × (1 + Growth rate), net profit = Revenue × Net interest rate (formula format)
        ws.cell(row=r, column=2, value=f"=B{r - 1}*(1+C{r})").number_format = "#,##0.0"
        growth_cell = ws.cell(row=r, column=3, value=float(a["revenue_growth"]))
        growth_cell.number_format = "0.0%"
        growth_cell.fill = _INPUT_FILL
        margin_cell = ws.cell(row=r, column=4, value=float(a["net_margin"]))
        margin_cell.number_format = "0.0%"
        margin_cell.fill = _INPUT_FILL
        ws.cell(row=r, column=5, value=f"=B{r}*D{r}").number_format = "#,##0.0"
        ws.cell(row=r, column=6, value=a.get("rationale", ""))
        period_row[a["period"]] = r
        r += 1

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 11
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 46
    return period_row


def _render_valuation_sheet(ws, spec: dict, period_row: Dict[str, int]) -> None:
    """Render valuation scenario Sheet (EPS cross-Sheet reference profit deduction)"""
    ws.title = SHEET_VALUATION
    ws["A1"] = f"Valuation scenario — {spec['stock_name']}"
    ws["A1"].font = Font(bold=True, size=13)

    ws["A2"] = "Total share capital (100 million shares)"
    ws["A2"].font = _BOLD
    share_cell = ws["B2"]
    share_cell.value = float(spec["share_count"])
    share_cell.number_format = "#,##0.00"
    share_cell.fill = _INPUT_FILL

    ws["A3"] = "Current price (yuan)"
    ws["A3"].font = _BOLD
    ws["B3"] = float(spec["current_price"])
    ws["B3"].number_format = "#,##0.00"

    headers = ["Scenario", "method", "multiple", "EPS base period", "EPS (Yuan)", "Target price (yuan)", "baseline", "Suitability check"]
    header_row = 5
    for c, h in enumerate(headers, start=1):
        ws.cell(row=header_row, column=c, value=h)
    _style_header(ws, header_row, len(headers))

    r = header_row + 1
    for s in spec["valuation"]["scenarios"]:
        src_row = period_row[s["eps_period"]]
        ws.cell(row=r, column=1, value=s["name"])
        ws.cell(row=r, column=2, value=str(s["method"]).upper()).alignment = _CENTER
        multiple_cell = ws.cell(row=r, column=3, value=float(s["multiple"]))
        multiple_cell.number_format = "0.0"
        multiple_cell.fill = _INPUT_FILL
        ws.cell(row=r, column=4, value=s["eps_period"]).alignment = _CENTER
        # EPS = Net profit (profit deduction!E)  ÷ Total share capital ($B$2) ; target price = EPS × multiple
        ws.cell(row=r, column=5, value=f"={SHEET_EARNINGS}!E{src_row}/$B$2").number_format = "#,##0.00"
        ws.cell(row=r, column=6, value=f"=E{r}*C{r}").number_format = "#,##0.00"
        ws.cell(row=r, column=7, value=s.get("benchmark_basis", ""))
        check = s.get("applicability_check") or {}
        if check.get("passed"):
            notes = "、".join(check.get("notes") or [])
            ws.cell(row=r, column=8, value=f"Pass{(': ' + notes) if notes else ''}")
        else:
            ws.cell(row=r, column=8, value=f"Failed:{check.get('notes') or 'see specs'}")
        r += 1

    for col, w in zip("ABCDEFGH", (8, 7, 8, 13, 10, 12, 40, 30)):
        ws.column_dimensions[col].width = w


def render_valuation_excel(spec: Dict[str, Any], output_path: str) -> str:
    """The rendering model specification is xlsx (verify the specification first, throw a ValuationSpecError if the specification is illegal)"""
    errors = validate_spec(spec)
    if errors:
        raise ValuationSpecError("Specification verification failed:\n- " + "\n- ".join(errors))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    period_row = _render_earnings_sheet(wb.active, spec)
    _render_valuation_sheet(wb.create_sheet(), spec, period_row)
    wb.save(path)
    return str(path)


# ==================== File verification ====================

def _is_formula(ws, row: int, col: int) -> bool:
    v = ws.cell(row=row, column=col).value
    return isinstance(v, str) and v.startswith("=")


def validate_valuation_excel(spec: Dict[str, Any], output_path: str) -> Dict[str, Any]:
    """Reopen xlsx verification: formula existence/input consistency/self-consistent calculation/target price range

    Returns:
        {passed, errors: [...], warnings: [...], summary: {...}}
    """
    errors: List[str] = []
    warnings: List[str] = []
    period_row: Dict[str, int] = {}

    wb = load_workbook(output_path)
    if SHEET_EARNINGS not in wb.sheetnames or SHEET_VALUATION not in wb.sheetnames:
        return {"passed": False,
                "errors": [f"Missing worksheet (expected {SHEET_EARNINGS} / {SHEET_VALUATION}, actual {wb.sheetnames}) "],
                "warnings": [], "summary": {}}
    ws_e, ws_v = wb[SHEET_EARNINGS], wb[SHEET_VALUATION]

    # ---- Sheet1: historical value + Forecast formula ----
    r = 4
    for h in spec["earnings_forecast"]["history"]:
        if ws_e.cell(row=r, column=1).value != h["period"]:
            errors.append(f"Profit deduction No. {r} The execution period is inconsistent with the specifications")
            break
        if abs(float(ws_e.cell(row=r, column=2).value) - float(h["revenue"])) > _EPS_TOL:
            errors.append(f"Profit deduction {h['period']} Revenue input value is inconsistent with specifications")
        if abs(float(ws_e.cell(row=r, column=5).value) - float(h["net_profit"])) > _EPS_TOL:
            errors.append(f"Profit deduction {h['period']} Net profit input value is inconsistent with specifications")
        period_row[h["period"]] = r
        r += 1

    prev_r = r - 1
    for a in spec["earnings_forecast"]["assumptions"]:
        if ws_e.cell(row=r, column=1).value != a["period"]:
            errors.append(f"Profit deduction No. {r} The execution period is inconsistent with the specifications")
            break
        # Formula existence: Revenue and net profit must be in formula grid
        for col, name in ((2, "Revenue"), (5, "net profit")):
            if not _is_formula(ws_e, r, col):
                errors.append(f"Profit deduction {a['period']} {name}Not a formula grid (may be written as a dead value)")
        # Correctness of formula citation: refer to the previous period's revenue and current period's assumptions
        rev_f = str(ws_e.cell(row=r, column=2).value)
        if f"B{prev_r}" not in rev_f or f"C{r}" not in rev_f:
            errors.append(f"Profit deduction {a['period']} Revenue formula citation error:{rev_f}")
        profit_f = str(ws_e.cell(row=r, column=5).value)
        if f"B{r}" not in profit_f or f"D{r}" not in profit_f:
            errors.append(f"Profit deduction {a['period']} Net profit formula reference error:{profit_f}")
        # Input consistency: Assume the grid is consistent with the specification
        if abs(float(ws_e.cell(row=r, column=3).value) - float(a["revenue_growth"])) > _EPS_TOL:
            errors.append(f"Profit deduction {a['period']} The input value of speed increase is inconsistent with the specification.")
        if abs(float(ws_e.cell(row=r, column=4).value) - float(a["net_margin"])) > _EPS_TOL:
            errors.append(f"Profit deduction {a['period']} Net profit margin input value is inconsistent with specifications")
        period_row[a["period"]] = r
        prev_r = r
        r += 1

    # ---- Sheet2: parameters + scenario formula ----
    if abs(float(ws_v["B2"].value) - float(spec["share_count"])) > _EPS_TOL:
        errors.append("Valuation scenario total equity input value is inconsistent with specifications")
    if abs(float(ws_v["B3"].value) - float(spec["current_price"])) > _EPS_TOL:
        errors.append("Valuation scenario current price input value is inconsistent with specifications")

    # Self-consistent calculation: Python recalculates expected EPS / target price (check the value chain corresponding to the logic of the formula)
    expected: Dict[str, Tuple[float, float]] = {}
    r = 6
    for s in spec["valuation"]["scenarios"]:
        if ws_v.cell(row=r, column=1).value != s["name"]:
            errors.append(f"Valuation Scenario No. {r} Row name is inconsistent with specification")
            break
        if not _is_formula(ws_v, r, 5) or not _is_formula(ws_v, r, 6):
            errors.append(f"Valuation Scenario {s['name']}] EPS Or the target price is not a formula")
        eps_f = str(ws_v.cell(row=r, column=5).value)
        src_row = period_row.get(s["eps_period"])
        if src_row is None or f"{SHEET_EARNINGS}!E{src_row}" not in eps_f or "$B$2" not in eps_f:
            errors.append(f"Valuation Scenario {s['name']}] EPS Formula reference error:{eps_f}")
        price_f = str(ws_v.cell(row=r, column=6).value)
        if f"E{r}" not in price_f or f"C{r}" not in price_f:
            errors.append(f"Valuation Scenario {s['name']}] Target price formula reference error:{price_f}")
        if abs(float(ws_v.cell(row=r, column=3).value) - float(s["multiple"])) > _EPS_TOL:
            errors.append(f"Valuation Scenario {s['name']}] The multiple input value is inconsistent with the specifications")
        # Recalculate
        profit = _forecast_net_profit(spec, s["eps_period"])
        if profit is not None:
            eps = profit / float(spec["share_count"])
            target = eps * float(s["multiple"])
            expected[s["name"]] = (eps, target)
            if target < 0.2 * float(spec["current_price"]) or target > 5 * float(spec["current_price"]):
                warnings.append(
                    f"Scenario {s['name']}] target price {target:.2f} Yuan deviation from current price {spec['current_price']} Yuan "
                    f"±80% Above, it is recommended to review the assumptions"
                )
        r += 1

    return {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "scenarios": {k: {"eps": round(v[0], 4), "target_price": round(v[1], 2)}
                          for k, v in expected.items()},
        },
    }


# ==================== Skill entrance (module+function for registration) ====================

def generate_valuation_excel(spec_json: str, output_path: str = "") -> str:
    """Skill entrance: specification JSON string → Generate and verify xlsx and return JSON results

    For Skill System module+function method registration call;
    The sandbox/skill caller parses stdout JSON to obtain the file path and verification conclusion.
    """
    import json

    try:
        spec = json.loads(spec_json) if isinstance(spec_json, str) else spec_json
    except Exception as e:
        return json.dumps({"success": False, "stage": "spec_parse", "error": f"Spec JSON parsing failed: {e}"},
                          ensure_ascii=False)

    if not output_path:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(Path("data") / "deliverables" / f"valuation_{spec.get('ticker', 'unknown')}_{ts}.xlsx")

    try:
        path = render_valuation_excel(spec, output_path)
    except ValuationSpecError as e:
        return json.dumps({"success": False, "stage": "spec_validation", "error": str(e)},
                          ensure_ascii=False)

    report = validate_valuation_excel(spec, path)
    report.update({"success": report["passed"], "stage": "file_validation", "path": path})
    return json.dumps(report, ensure_ascii=False)
