"""
Reflective mode prompt templates are centrally managed.

Transformed based on the 4-dimensional framework (Reasoning/Improvement/Summary/Query) of the old tradingagents/graph/reflection.py,
remove"ex post benefit"dependency, changed to"Conclusion vs trend"dimensions.

Three scenes:
- TRADE_REFLECTION: After the review is completed (item 2)
- ANALYSIS_REFLECTION: After the researcher report is generated (item 3)
- DEBATE_REFLECTION: After the debate (item 8)

All prompts require strict JSON output to facilitate program parsing and mem0 structured storage.
"""

from typing import Any, Dict, List, Optional


# ============================================================
# System Prompts
# ============================================================

TRADE_REFLECTION_SYSTEM_PROMPT = """You are an expert in trading reflection. Based on the following review conclusions, reusable structured experience is extracted.

## Output format (strictly JSON)
{
  "reasoning": "What is the core logic of this transaction? Which judgments have been verified by the market? Which ones have been disproven? (50-150 words)",
  "improvement": "Which judgments were wrong? How should we improve next time we encounter a similar situation? (50-150 words)",
  "summary": "Summarize the core lessons of this transaction in one sentence (20-50 words)",
  "query": "Keywords that can be used for vector search, separated by commas (10-20 words)"
}

## request
1. Output only JSON and no other content (no ```json Mark, don t explain)
2. Refining based on review conclusions, do not make up information that has not been given
3. Lessons should be reusable, not just about the details of a single transaction
4. If the review conclusion information is insufficient, reasoning/improvement can be filled in."Insufficient information to reflect deeply"
"""

ANALYSIS_REFLECTION_SYSTEM_PROMPT = """You are an expert in investment research reflection. Based on the following analysis report, reusable structured lessons are extracted.

## Output format (strictly JSON)
{
  "reasoning": "What is the core idea of this analysis? What is the basis? (50-150 words)",
  "improvement": "What dimensions might be missing from the analysis? What should I add next time? (50-150 words)",
  "summary": "Summarize the core lessons of this analysis in one sentence (20-50 words)",
  "query": "Keywords that can be used for vector search, separated by commas (10-20 words)"
}

## request
1. Output only JSON and no other content (no ```json Mark, don t explain)
2. Extract based on the content of the report and do not make up information that is not given.
3. Lessons should be oriented towards"Analysis of the same stock or industry next time"Reusable
4. If the report information is insufficient, reasoning/improvement can be filled in"Insufficient information to reflect deeply"
"""

DEBATE_REFLECTION_SYSTEM_PROMPT = """You are an expert in debate reflection. Based on the debate history and final verdict below, distill new ideas and lessons learned from the debate.

## Output format (strictly JSON)
{
  "reasoning": "What valuable new ideas were raised in the debate? Which points were adopted in the final ruling? (50-150 words)",
  "improvement": "Which perspectives are being ignored? Was the debate sufficient? What should be added to the next similar debate? (50-150 words)",
  "summary": "Summarize the core lessons of this debate in one sentence (20-50 words)",
  "query": "Keywords that can be used for vector search, separated by commas (10-20 words)"
}

## request
1. Output only JSON and no other content (no ```json Mark, don t explain)
2. Based on the history of debates and rulings, do not make up information that is not given
3. Lessons should be oriented towards"Next time debate about stocks or the same industry"Reusable
4. If there is insufficient debate information, reasoning/improvement can be filled in"Insufficient information to reflect deeply"
"""


# ============================================================
# User Prompt builder
# ============================================================

def build_trade_reflection_user_prompt(
    trade_info: Any,
    ai_review: Any,
) -> str:
    """Construct a user prompt for review and reflection.

    Args:
        trade_info: Transaction information object (with attributes such as code/name/first_buy_date)
        ai_review: AI Review conclusion (with summary/strengths/weaknesses/suggestions/plan_deviation attributes)

    Returns:
        user prompt text
    """
    code = getattr(trade_info, "code", "") or ""
    name = getattr(trade_info, "name", "") or ""
    first_buy = getattr(trade_info, "first_buy_date", "") or ""

    summary = (getattr(ai_review, "summary", "") or "").strip()
    strengths = list(getattr(ai_review, "strengths", []) or [])
    weaknesses = list(getattr(ai_review, "weaknesses", []) or [])
    suggestions = list(getattr(ai_review, "suggestions", []) or [])
    plan_deviation = (getattr(ai_review, "plan_deviation", "") or "").strip()

    parts = [f"## Transaction object:{name}({code}), First time purchase:{first_buy}"]
    if summary:
        parts.append(f"### Review summary\n{summary}")
    if strengths:
        parts.append("### Things done well\n" + "\n".join(f"- {s}" for s in strengths[:5] if s))
    if weaknesses:
        parts.append("### shortcomings\n" + "\n".join(f"- {w}" for w in weaknesses[:5] if w))
    if plan_deviation:
        parts.append(f"### plan deviation\n{plan_deviation[:500]}")
    if suggestions:
        parts.append("### Improvement suggestions\n" + "\n".join(f"- {s}" for s in suggestions[:5] if s))

    return "\n\n".join(parts)


def build_analysis_reflection_user_prompt(
    ticker: str,
    report: Any,
    analysis_date: str = "",
) -> str:
    """Constructing user prompts for researcher report reflections.

    Args:
        ticker: Stock code
        report: research report (dict or string)
        analysis_date: Analysis date

    Returns:
        user prompt text
    """
    # Extract report content
    if isinstance(report, dict):
        content = report.get("content", "") or report.get("report", "") or str(report)
        stance = report.get("stance", "")
    else:
        content = str(report)
        stance = ""

    # Truncate overly long content (to avoid wasting tokens)
    max_chars = 2000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n...(Content has been truncated)"

    parts = [f"## Stocks:{ticker}, Analysis date:{analysis_date or 'unknown'}"]
    if stance:
        stance_label = {"bull": "optimistic", "bear": "Prudence", "risky": "High elasticity", "safe": "defense", "neutral": "Baseline scenario"}.get(stance, stance)
        parts.append(f"### Research position:{stance_label}")
    parts.append(f"### analysis report\n{content}")

    return "\n\n".join(parts)


def build_debate_reflection_user_prompt(
    ticker: str,
    debate_history: str,
    conclusion: str,
    debate_type: str = "",
) -> str:
    """User prompts for building multi-scenario research reflections.

    Args:
        ticker: Stock code
        debate_history: Multi-scenario research on historical texts
        conclusion: final verdict/conclusion
        debate_type: Multiple scenario study types (investment_debate / risk_debate)

    Returns:
        user prompt text
    """
    # Truncate too much scenario study history
    max_chars = 3000
    if len(debate_history) > max_chars:
        debate_history = debate_history[:max_chars] + "\n...(Multi-scenario research history has been truncated)"

    if len(conclusion) > max_chars:
        conclusion = conclusion[:max_chars] + "\n...(Conclusion has been truncated)"

    debate_label = {
        "investment_debate_state": "multi-scenario research",
        "risk_debate_state": "Risk multi-scenario research",
    }.get(debate_type, debate_type or "multi-scenario research")

    parts = [
        f"## Stocks:{ticker}",
        f"### Multiple scenario study types:{debate_label}",
        f"### Multi-scenario research history\n{debate_history}",
        f"### final verdict\n{conclusion}",
    ]

    return "\n\n".join(parts)
