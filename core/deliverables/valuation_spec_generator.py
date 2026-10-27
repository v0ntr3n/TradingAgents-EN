"""Valuation calculation specification generation layer (A10-D1 piece ①) 

The specification generation layer in the three-tier architecture: LLM (Seed-Evolving) extracts judgment from the research report package,
Output model specifications JSON; historical data, current price, and total equity are injected by the pipeline (real data anchor,
The model only generates judgment class fields——Forecast assumptions and valuation scenarios), compressing the illusion surface.

Automatic feedback and retries for verification failures (aligned with the iterative repair narrative of the Skill generation pipeline).
See valuation_excel.py for the deterministic layer.
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from core.llm.models import Message

from .valuation_excel import (
    ValuationSpecError,
    render_valuation_excel,
    validate_spec,
    validate_valuation_excel,
)

logger = logging.getLogger(__name__)

# ==================== prompt word ====================

SPEC_SYSTEM_PROMPT = """You are a rigorous valuation modeling analyst. Your task: Based on the conclusions of the research report and structured financial data, produce the model specification (JSON) of the valuation calculation table.

Division of labor boundaries (highest priority):
- Historical financial data, current prices, and total equity are injected by the system. You are not allowed to fabricate, alter, or export these fields.
- You only output judgment fields: forecast assumptions, valuation scenarios and risk warnings for the next two years

Output requirements:
- Only output a JSON object, no markdown fence, no explanation text
- JSON Contains only two fields: earnings_forecast,valuation

Field specifications:
1. earnings_forecast.assumptions: Array of forecasts for the next 2 years, each item:
   - period: Year+E, Such as "2026E", "2027E" (Connected with the forecast starting point)
   - revenue_growth: Year-on-year revenue growth rate, decimal (0.25 means 25%); required > -1 And not for 0
   - net_margin: Net interest rate, decimal; must be within (0, 1] range and not 0
   - rationale: 50 The in-text basis must cite specific arguments in research materials, and no fabrication of extra-material data is allowed.
2. valuation.scenarios: At least 3 scenarios (pessimistic/neutral/optimistic), each:
   - name: scene name
   - method: fixed to "PE"
   - multiple: PE multiple, must be positive
   - eps_period: EPS Base period, must be the given historical period or one of your forecast periods
   - benchmark_basis: Comparison benchmark (peer range, historical quantile, etc., source must be explained)
   - applicability_check: {"passed": true, "notes": ["Net profit attributable to parent company is positive"]} (PE Net profit in the base period is required to be positive)
3. valuation.risk_notes: 3-5 risk warning

Method applicability (must self-check):
- Net profit during the forecast period = Revenue of the previous period × (1 + Growth rate) × Net profit margin (revenue rolling from period to period)
- PE If the eps_period falls in the loss period, it must be replaced by the profit period.

Numerical discipline:
- The direction of the hypothesis must be consistent with the research conclusion (neutral conclusions should not be given to extreme hypotheses)
- The multiple must be based on a benchmark and cannot be given out of thin air."""

# Material truncation upper limit (chars)
_MAX_PLAN = 2500
_MAX_FUNDAMENTALS = 2500
_MAX_RESEARCHER = 1500


def _truncate(text: Any, limit: int) -> str:
    s = str(text or "").strip()
    return s if len(s) <= limit else s[:limit] + "… (Truncated later)"


def build_spec_user_prompt(bundle: Dict[str, Any]) -> str:
    """Assembly specifications generate user prompt words (structured data + research materials)"""
    hist_rows = "\n".join(
        f"  | {h['period']} | {h['revenue']:.1f} | {h['net_profit']:.2f} |"
        for h in bundle["financial_history"]
    )
    last_period = bundle["financial_history"][-1]["period"]

    return f""" [Stocks]{bundle['stock_name']} ({bundle['ticker']})  Analysis date:{bundle.get('analysis_date', '')}

 [Structured data (system injection, real value, modification prohibited)] 
- Current price:{bundle['current_price']} Yuan
- Total share capital:{bundle['share_count']} 100 million shares
- Financial history (unit: 100 million yuan):
  | period | Revenue | Net profit attributable to parent company |
{hist_rows}
- Net profit calculation chain during the forecast period:{last_period}Revenue × (1+Growth rate) × Net interest rate, rolling period by period

 [Comprehensive research conclusion]
{_truncate(bundle.get('investment_plan'), _MAX_PLAN)}

 [Key points of fundamental analysis]
{_truncate(bundle.get('fundamentals_report'), _MAX_FUNDAMENTALS)}

 [Key Points for Optimistic Researchers]
{_truncate(bundle.get('bull_report'), _MAX_RESEARCHER)}

 [Points for prudent researchers]
{_truncate(bundle.get('bear_report'), _MAX_RESEARCHER)}

Please output the model specification JSON (containing only earnings_forecast and valuation fields, no fences and no explanation)."""


# ==================== Parse and merge ====================

def extract_json_block(text: str) -> Optional[dict]:
    """Extract JSON from model output (compatible with fences, pre- and post-text)"""
    if not text or not text.strip():
        return None
    candidates: List[str] = []
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        candidates.append(m.group(1))
    s, e = text.find("{"), text.rfind("}")
    if s >= 0 and e > s:
        candidates.append(text[s:e + 1])
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def merge_spec(model_output: Dict[str, Any], bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Merge model output and injected data: real data fields are always subject to bundle"""
    ef = model_output.get("earnings_forecast") or {}
    val = model_output.get("valuation") or {}
    return {
        "ticker": bundle["ticker"],
        "stock_name": bundle["stock_name"],
        "analysis_date": bundle.get("analysis_date", ""),
        "share_count": bundle["share_count"],
        "current_price": bundle["current_price"],
        "earnings_forecast": {
            "history": bundle["financial_history"],
            "assumptions": ef.get("assumptions") or [],
        },
        "valuation": val,
    }


# ==================== Generate (retry with feedback) ====================

def generate_valuation_spec(
    bundle: Dict[str, Any],
    llm: Any,
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """Call LLM to generate model specifications. If verification fails, automatic feedback will be given to try again.

    Args:
        bundle: The report package (financial_history/current_price/share_count is the real data injected;
                investment_plan/fundamentals_report/bull_report/bear_report for research materials)
        llm: Have .chat(messages) -> response(.content) Client (UnifiedLLMClient)
        max_attempts: Maximum number of attempts

    Returns:
        {passed, spec, attempts, errors, elapsed}
    """
    t0 = time.time()
    messages: List[Message] = [
        Message(role="system", content=SPEC_SYSTEM_PROMPT),
        Message(role="user", content=build_spec_user_prompt(bundle)),
    ]
    last_errors = ["Not called LLM"]

    for attempt in range(1, max_attempts + 1):
        resp = llm.chat(messages)
        text = getattr(resp, "content", None)
        if text is None:
            text = resp if isinstance(resp, str) else ""
        parsed = extract_json_block(text)
        if parsed is None:
            last_errors = ["Output cannot be parsed as JSON (may contain unfenced text or be malformed)"]
        else:
            spec = merge_spec(parsed, bundle)
            last_errors = validate_spec(spec)
            if not last_errors:
                logger.info(f"[ValuationSpec] Specifications generated successfully (No. {attempt} attempts)")
                return {"passed": True, "spec": spec, "attempts": attempt,
                        "errors": [], "elapsed": time.time() - t0}
        logger.warning(f"[ValuationSpec] No. {attempt} failed attempts: {last_errors}")

        # Feedback retry: pass errors back to the model for correction
        messages.append(Message(role="assistant", content=str(text)[:4000]))
        messages.append(Message(
            role="user",
            content="The last output has the following issues:\n- " + "\n- ".join(last_errors)
                    + "\n Please correct and re-output the complete JSON (only earnings_forecast and valuation, no fences and no explanation).",
        ))

    return {"passed": False, "spec": None, "attempts": max_attempts,
            "errors": last_errors, "elapsed": time.time() - t0}


# ==================== end-to-end portal ====================

def generate_valuation_deliverable(
    bundle: Dict[str, Any],
    llm: Any,
    output_path: str = "",
    max_attempts: int = 3,
) -> Dict[str, Any]:
    """End-to-end: reporting package → LLM Specification generation → rendering xlsx → File verification

    Provides the intelligent assistant layer with declarative deliverable scheduling (demo link 5 link).
    """
    spec_result = generate_valuation_spec(bundle, llm, max_attempts=max_attempts)
    if not spec_result["passed"]:
        return {"success": False, "stage": "spec_generation",
                "attempts": spec_result["attempts"], "errors": spec_result["errors"]}

    spec = spec_result["spec"]
    if not output_path:
        from datetime import datetime
        from pathlib import Path
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = str(Path("data") / "deliverables"
                          / f"valuation_{spec['ticker']}_{ts}.xlsx")

    try:
        path = render_valuation_excel(spec, output_path)
    except ValuationSpecError as e:  # Passed validate_spec, theoretically unreachable, defensive
        return {"success": False, "stage": "render", "error": str(e)}

    report = validate_valuation_excel(spec, path)
    return {
        "success": report["passed"],
        "stage": "file_validation",
        "attempts": spec_result["attempts"],
        "spec": spec,
        "validation": report,
        "path": path,
    }
