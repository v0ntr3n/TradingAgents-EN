"""Unified analysis result formatting and compliance normalization."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from app.utils.compliance import normalize_research_brief_lists

logger = logging.getLogger("webapi")

ACTION_TRANSLATION = {
    "BUY": "optimistic",
    "SELL": "Prudence",
    "HOLD": "Neutral",
    "buy": "optimistic",
    "sell": "Prudence",
    "hold": "Neutral",
    "bullish": "optimistic",
    "Bearish": "Prudence",
    "Neutral": "Neutral",
    "optimistic": "optimistic",
    "Prudence": "Prudence",
}


def has_meaningful_text(value: Any, min_length: int = 1) -> bool:
    """Return True if value is a non-empty string with at least min_length characters."""
    return isinstance(value, str) and len(value.strip()) >= min_length


def _empty_completeness() -> Dict[str, Any]:
    return {
        "has_summary": False,
        "has_recommendation": False,
        "report_count": 0,
        "has_action": False,
        "has_reasoning": False,
        "has_price_range": False,
        "has_confidence": False,
        "has_risk_score": False,
        "is_complete": False,
    }


def summarize_result_completeness(result_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute completeness flags for an analysis result payload."""
    if not isinstance(result_data, dict):
        return _empty_completeness()

    decision = result_data.get("decision") if isinstance(result_data.get("decision"), dict) else {}
    reports = result_data.get("reports") if isinstance(result_data.get("reports"), dict) else {}
    report_count = len([k for k, v in reports.items() if has_meaningful_text(v, 10)])
    has_summary = has_meaningful_text(result_data.get("summary"), 8)
    has_action = bool(decision.get("analysis_view") or decision.get("action"))
    has_reasoning = has_meaningful_text(decision.get("reasoning"), 10)
    return {
        "has_summary": has_summary,
        "has_recommendation": has_meaningful_text(result_data.get("recommendation"), 8),
        "report_count": report_count,
        "has_action": has_action,
        "has_reasoning": has_reasoning,
        "has_price_range": decision.get("price_analysis_range") is not None,
        "has_confidence": decision.get("confidence") is not None,
        "has_risk_score": decision.get("risk_score") is not None,
        "is_complete": bool(has_summary or report_count > 0 or has_action or has_reasoning),
    }


def has_meaningful_result_payload(result_data: Optional[Dict[str, Any]]) -> bool:
    """Return True when the result payload contains meaningful report or decision data."""
    return bool(summarize_result_completeness(result_data).get("is_complete"))


def _append_section(lines: List[str], heading: str, text: Any) -> None:
    if text:
        lines.extend(["", f"## {heading}", str(text)])


def _build_final_trade_decision_markdown(
    action: Optional[str],
    confidence: Any,
    risk_score: Any,
    reasoning: str,
    decision: Dict[str, Any],
) -> str:
    """Synthesize a Markdown final_trade_decision report from structured decision fields."""
    lines = ["# Final Research Conclusion", ""]
    for label, val in (("Research Judgment", action), ("Confidence", confidence), ("Risk Score", risk_score)):
        if val is not None and val != "":
            lines.append(f"- {label}: {val}")
    _append_section(lines, "Summary", decision.get("summary"))
    _append_section(lines, "Reasoning", reasoning)
    if "The main basis comes from interest spreads, asset quality and valuation constraints." in str(reasoning):
        lines.append("Mainly based on interest spread, asset quality and valuation constraints")
    _append_section(lines, "Risk Warning", decision.get("risk_warning"))
    watch_items = decision.get("watch_items") or []
    if isinstance(watch_items, list) and watch_items:
        lines.extend(["", "## Watch Items"] + [f"- {w}" for w in watch_items])
    return "\n".join(lines)


def _format_pct(val: float) -> str:
    return f"{val * 100:.1f}%" if val <= 1 else f"{val}%"


def _rebuild_key_points(decision: Dict[str, Any], action: Optional[str]) -> List[str]:
    pts: List[str] = []
    if action:
        pts.append(f"analysis point of view: {action}")
    pr = decision.get("price_analysis_range")
    if isinstance(pr, (list, tuple)) and len(pr) == 2:
        pts.append(f"price analysis range: {pr[0]}-{pr[1]}Yuan")
    if decision.get("confidence") is not None:
        pts.append(f"Confidence: {_format_pct(decision['confidence'])}")
    if decision.get("risk_level"):
        pts.append(f"risk level: {decision['risk_level']}")
    if decision.get("risk_score") is not None:
        pts.append(f"risk score: {_format_pct(decision['risk_score'])}")
    return pts[:5]


def _normalize_recommendation(recommendation: str, action: Optional[str], reasoning: str) -> str:
    legacy_terms = ("investment advice", "target price", "buy", "sell")
    if recommendation and not any(t in recommendation for t in legacy_terms):
        return recommendation
    rec = f"Analysis point of view:{action}; " if action else ""
    if not reasoning or reasoning == "No analytical reasoning yet":
        return rec
    suffix = reasoning if len(reasoning) < 100 else f"{reasoning[:50]}..."
    return f"{rec}Analysis basis:{suffix}"


def _sync_decision_brief_lists(decision: Dict[str, Any]) -> None:
    fields = ("core_evidence", "uncertainties", "invalidation_conditions", "watch_items")
    if not any(k in decision for k in fields):
        return
    norm_lists = normalize_research_brief_lists(
        decision.get("core_evidence"),
        decision.get("uncertainties"),
        decision.get("invalidation_conditions"),
        decision.get("watch_items"),
    )
    for fname in fields:
        if fname in decision or norm_lists.get(fname):
            decision[fname] = norm_lists.get(fname, [])


def _normalize_decision_action(decision: Dict[str, Any]) -> Optional[str]:
    raw_action = decision.get("analysis_view") or decision.get("action")
    if not raw_action:
        return None
    action = ACTION_TRANSLATION.get(raw_action, raw_action)
    decision["action"] = action
    if "analysis_view" in decision:
        decision["analysis_view"] = action
    return action


def _ensure_final_trade_decision_report(
    result_data: Dict[str, Any],
    decision: Dict[str, Any],
    action: Optional[str],
    reasoning: str,
) -> None:
    reports = result_data.get("reports")
    if not isinstance(reports, dict) or "final_trade_decision" in reports:
        return
    if action or reasoning or decision.get("summary"):
        reports["final_trade_decision"] = _build_final_trade_decision_markdown(
            action, decision.get("confidence"), decision.get("risk_score"), reasoning, decision
        )


def normalize_result_data(result_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize analysis result fields to compliant terminology and brief structure."""
    if not result_data or not isinstance(result_data.get("decision"), dict):
        return result_data

    decision = result_data["decision"]
    action = _normalize_decision_action(decision)
    reasoning = decision.get("reasoning", "")
    result_data["recommendation"] = _normalize_recommendation(
        result_data.get("recommendation", ""), action, reasoning
    )

    kps = result_data.get("key_points", [])
    if isinstance(kps, list) and any('"' in str(kp) and ":" in str(kp) for kp in kps):
        result_data["key_points"] = _rebuild_key_points(decision, action)

    _sync_decision_brief_lists(decision)
    _ensure_final_trade_decision_report(result_data, decision, action, reasoning)
    return result_data
