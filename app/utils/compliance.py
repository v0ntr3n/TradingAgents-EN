"""Compliance output tool.

Unify transaction recommendation fields in closing analysis results, retaining summaries, risk factors, and public information observations required for research assistance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple


SAFE_REPORT_KEYS = (
    "index_report",
    "sector_report",
    "market_report",
    "fundamentals_report",
    "sentiment_report",
    "news_report",
)

GENERIC_RESEARCH_RECOMMENDATION = "Please refer to the detailed research report, focusing on fundamental changes, market environment and risk factors."
GENERIC_POSITION_RECOMMENDATION = "This position research only provides research observations and risk tips. Please make independent judgments based on your own strategies."
GENERIC_REVIEW_SUMMARY = "This review only retains the review conclusions, disciplinary issues and research and improvement directions, and does not provide suggestions for future trading actions."
GENERIC_REVIEW_IMPROVEMENTS = (
    "Improve pre-transaction evidence verification and recording to avoid insufficient basis for pre-transaction transactions.",
    "Organize the triggering conditions of the trading plan into a verifiable list to improve execution consistency.",
    "During the review, the focus will be on discipline enforcement, risk exposure and research blind spots.",
)

_ACTIONABLE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"buy|sell|hold|Add to position|Reduce positions|Clearance|Open a position|Close position|Adjust positions",
        r"stop loss|Take profit|position|target price|target price|target range|price analysis range|reference price",
        r"Target position|target point|support level|resistance level|pressure level|Configuration recommendations|defensive configuration|offensive configuration|margin of safety|Sector opportunities",
        r"investment advice|trading advice|Operation suggestions|Simulate an order with one click|Place an order|simulated trading",
        r"BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL",
        r"target_price|stop_loss|take_profit|position_ratio|suggested_quantity|suggested_amount",
    )
]
_REVIEW_EXECUTION_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(Suggestions|OK|Can be considered|should|should|need|appropriate|Not suitable).{0,12}(buy|sell|continue to hold|hold|Add to position|Reduce positions|cover position|Clearance|Open a position|Close position|Adjust positions)",
        r"(next time|Follow-up|future).{0,16}(buy|sell|continue to hold|hold|Add to position|Reduce positions|cover position|Clearance|Open a position|Close position|Adjust positions|stop loss|Take profit)",
        r"continue to hold|buy on dips|sell on rallies|Buy in batches|Sell in batches",
        r"Stop loss price|Take profit price|target price|target price|target range|reference price|reference price",
        r"(fell below|breakthrough|call back to|rebound to|fall to|rise to|return to).{0,12}(buy|sell|Add to position|Reduce positions|stop loss|Take profit)",
        r"position.{0,8}(\d+%|percent|\d+into|controlled in|promoted to|down to|raised to|Adjusted down to)",
        r"\b(BUY|SELL|HOLD|STRONG_BUY|STRONG_SELL)\b",
        r"Simulate an order with one click|Place an order|simulated trading",
    )
]
_POSITION_TRIGGER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:technical aspect|Fundamentals|risk|Comprehensive)?Rating\s*[:: ]?\s*\d+(?:\.\d+)?\s*points",
        r"continuous.{0,8}(?:day|day|week).{0,10}(stand firm|Stand firm at the close|Increase the volume|shrink|breakthrough|fell below)",
        r"Right intervention|left intervention|Basis for intervention|Admission basis|Exit basis|Transaction trigger|rebound kinetic energy",
        r"\bMA\d+\b|\bRSI\d*\b|\bMACD\b|\bKDJ\b|Brin(?:middle track|On track|Lower track)?",
        r"support strap|support level|resistance level|pressure level|Increase the volume|shrink|stand firm|breakthrough|fell below",
    )
]
_POSITION_LABEL_ONLY_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^(Research conclusion|core basis|research judgment|Risk warning|Observation points|Supplementary perspective|research observation|risk assessment|Catalysis and improving conditions)$",
    )
]
_POSITION_PLAIN_LANGUAGE_REPLACEMENTS = (
    ("Technically highly secure", "The short-term trend has not weakened significantly"),
    ("Neutral to strong state", "The current status is relatively stable, but further verification is needed."),
    ("Technical structure is critically stable", "There is no further deterioration in the short term"),
    ("Solid fundamentals but differentiated valuation structure", "The company s operating foundation is acceptable, but the market is still divided on valuation restoration"),
    ("neutral observation stage", "For the time being, we can only continue to observe"),
    ("Prices cling to medium-term support", "The stock price is still near a periodic low"),
    ("No trend reversal signal has occurred yet", "No clear signal of repair has been seen yet"),
    ("Nor did it trigger conditions for systemic deterioration.", "There is no clear evidence of deterioration"),
    ("The cost price is significantly higher than the current price", "The current price is still significantly lower than the holding cost"),
    ("Cost price is buried deep below all key moving averages", "The current price is significantly higher than the holding cost"),
    ("Stable financial indicators and excellent earnings quality", "Overall operational and financial performance is stable"),
    ("Operating cash flow continues to cover net profit at a high multiple", "Cash flow performance is relatively stable"),
    ("Solid margin of financial safety", "Financial buffers remain solid"),
    ("Growth logic needs to be verified", "Whether subsequent growth will continue remains to be verified."),
    ("ROE staged decline", "Profit efficiency drops in stages"),
    ("Gross profit margin data is missing", "Margin data is incomplete"),
    ("High PB valuation", "current valuation level"),
    ("barrier premium", "competitive advantage premium"),
    ("growth premium", "growth expected premium"),
    ("Valuation center rises", "The market is willing to give a higher valuation"),
    ("second curve", "new business growth"),
    ("Customer designated announcement", "Announcement of new customers and project progress"),
    ("bargaining power", "pricing power"),
    ("Repair requires time and multiple conditions.", "Subsequent repairs usually take time and require improvements in many aspects."),
)
_POSITION_GENERIC_ITEM_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"The current judgment is mainly based on the disclosure of operating information and risk signals.",
        r"Current conclusions are primarily based on disclosed information",
        r"Please focus on",
        r"Please keep following",
        r"Follow-up key observations",
    )
]
_POSITION_APPENDIX_SECTION_ORDER = (
    ("technical_analysis", "Technical analysis"),
    ("fundamental_analysis", "fundamental analysis"),
    ("risk_analysis", "risk assessment"),
)
_POSITION_APPENDIX_TITLE_TO_KEY = {
    title: key for key, title in _POSITION_APPENDIX_SECTION_ORDER
}
_POSITION_APPENDIX_HEADING_PATTERN = re.compile(r"^ [(Technical analysis|fundamental analysis|risk assessment)] $")
_JSON_FIELD_PATTERN = re.compile(r'^[\[\]{}":,0-9._%\-\s]+$')
_SENTENCE_SPLIT_PATTERN = re.compile(r"[\n。！？；]+")
_LOW_SIGNAL_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^Basic stock information$",
        r"^Company name[:: ]",
        r"^Stock code[:: ]",
        r"^Market[:: ]",
        r"^current price[:: ]",
        r"^Increase or decrease[:: ]",
        r"^Analysis date[:: ]",
        r"^Data source[:: ]",
        r"^Basic information[:: ]",
        r"^financial data[:: ]$",
        r"^1. Company Profile$",
        r"^2. Financial data analysis$",
        r"^Three.",
        r"^Four.",
        r"analysis report",
    )
]
_DISPLAY_REPORT_RISK_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"target price|target price|price range|key price|key price|key verification bit|Observation interval|reference price|reference price|Risk Control Reference",
        r"support level|resistance level|breakthrough|fell below|stand firm|fall|stop loss|Take profit|position|risk exposure|Position period",
        r"Room for upside|Downside|Upside|Downside|Profit space|Earnings expectations|maximum benefit|Potential earnings|retracement|maximum possible loss",
        r"Risk-benefit ratio|expected return|margin of safety|configuration value|Contrarian investment opportunities|buy signal|sell signal|Admission|Exit conditions|Operational strategy",
        r"Overweight view|Underweight view|Open a position|Close position|Adjust positions|Heavy warehouse|Qingcang|Buy in batches|Sell in batches|bullish price|bearish price",
        r"(?:¥|￥|\$)\s*\d|\d+(?:\.\d+)?\s*(?:Yuan|US dollars|Hong Kong dollar)",
    )
]
_INFERENTIAL_EVIDENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"inference|Speculate|Presumption|Estimate|Calculate|estimate|hypothesis|Assume|Guess|conjecture|suspected",
        r"possible|or will|hopefully|expected|tend to|High probability|maybe|Maybe",
        r"To be verified|Need to verify|yet to be verified|Still to be verified|Not verifiable|Difficult to verify",
    )
]

_DISPLAY_TITLE_REPLACEMENTS = [
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?News Analyst Research Report$', re.IGNORECASE), 'Journalism Research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?news research report$', re.IGNORECASE), 'Journalism Research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Social Media Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Social Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Sentiment Analyst Research Report$', re.IGNORECASE), 'emotion research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Sector Analyst Research Observation Report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Industry Analyst Research Observation Report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Industry sector research observation report$', re.IGNORECASE), 'Industry sector research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Market Analyst Research Observation Report$', re.IGNORECASE), 'market environment research'),
    (re.compile(r'^(?P<prefix>#{1,6}\s*)?Market Environment Research Observation Report$', re.IGNORECASE), 'market environment research'),
]

_DISPLAY_PHRASE_REPLACEMENTS = (
    ('buy logic', 'research logic'),
    ('investment opportunities', 'research leads'),
    ('allocation investor', 'research users'),
    ('configuration value', 'Research tracking value'),
    ('margin of safety', 'risk buffer'),
    ('have certain appeal', 'Worth continuing to follow'),
    ('The starting point of value restoration', 'Early signs of valuation and expected repairs'),
)

RESEARCH_ONLY_DISCLAIMER = "This report is for research reference only and does not constitute individual stock recommendation, investment advice or operation basis. Please make independent judgments based on public information disclosure and your own research."
_LEGACY_DISCLAIMER_BLOCK_PATTERN = re.compile(
    r"(?is)(?:\*\*)?Disclaimer(?:\*\*)?[: :]\s*"
    r"(?:Ben(?:analysis)?The report is for reference only and does not constitute investment advice..*?Make investment decisions independently."
    r"|Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary.)"
)
_LEGACY_DISCLAIMER_LINE_PATTERN = re.compile(
    r"(?is)Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary."
)
_TOOL_CALL_ARTIFACT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"^</?tool_call>$",
        r'^\{"name"\s*:\s*"get_[^\"]+".*"arguments"\s*:\s*\{.*\}\s*\}$',
        r'^"name"\s*:\s*"get_[^\"]+"',
        r'^"arguments"\s*:\s*\{',
    )
]
_STABLE_DATA_REQUEST_DATE_PATTERNS = [
    re.compile(pattern)
    for pattern in (
        r"There are currently no analysis days[ ((](\d{4}-\d{2}-\d{2})[) )]Corresponding stable post-closing daily frequency data",
        r"None currently\s*(\d{4}-\d{2}-\d{2})\s*Corresponding stable post-closing daily frequency data",
        r"None currently\s*(\d{4}-\d{2}-\d{2})\s*of[^. \n]*Daily frequency data after stable closing",
    )
]
_STABLE_DATA_SNAPSHOT_LINE_PATTERN = re.compile(
    r"The snapshot date of all valuation indicators is unified to\s*(?:\*\*)?(\d{4}-\d{2}-\d{2})(?:\*\*)?[. .]?"
)


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("content", "markdown", "text", "message", "report"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        return ""
    return "" if value is None else str(value)


def contains_actionable_content(text: str) -> bool:
    if not text:
        return False
    return any(pattern.search(text) for pattern in _ACTIONABLE_PATTERNS)


def contains_review_execution_guidance(text: str) -> bool:
    if not text:
        return False
    normalized = _plain_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _REVIEW_EXECUTION_PATTERNS)


def _plain_text(text: Any) -> str:
    if text is None:
        return ""

    if isinstance(text, (list, tuple, set)):
        joined = " ".join(
            fragment
            for item in text
            for fragment in [_plain_text(item)]
            if fragment
        )
        if not joined:
            return ""
        text = joined
    elif isinstance(text, dict):
        text = _as_text(text)
    elif not isinstance(text, str):
        text = str(text)

    normalized = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    normalized = re.sub(r"`+", "", normalized)
    normalized = normalized.replace("#", " ").replace("*", " ")
    return re.sub(r"\s+", " ", normalized).strip()


def _normalize_display_line(line: str) -> str:
    normalized_line = line

    for pattern, replacement in _DISPLAY_TITLE_REPLACEMENTS:
        match = pattern.match(normalized_line.strip())
        if match:
            prefix = match.groupdict().get('prefix') or ''
            return f"{prefix}{replacement}".rstrip()

    for old_text, new_text in _DISPLAY_PHRASE_REPLACEMENTS:
        normalized_line = normalized_line.replace(old_text, new_text)

    return normalized_line


def _normalize_research_disclaimer(text: str) -> str:
    normalized = _LEGACY_DISCLAIMER_BLOCK_PATTERN.sub(
        f"**Disclaimer**: {RESEARCH_ONLY_DISCLAIMER}",
        text,
    )
    normalized = _LEGACY_DISCLAIMER_LINE_PATTERN.sub(RESEARCH_ONLY_DISCLAIMER, normalized)
    return normalized


def _strip_tool_call_artifacts(text: str) -> Tuple[str, bool]:
    cleaned_lines: List[str] = []
    removed_any = False

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        normalized = _plain_text(raw_line)

        if any(pattern.search(stripped) or pattern.search(normalized) for pattern in _TOOL_CALL_ARTIFACT_PATTERNS):
            removed_any = True
            continue

        if stripped.startswith("{") and '"name"' in stripped and '"arguments"' in stripped and '"get_' in stripped:
            removed_any = True
            continue

        cleaned_lines.append(raw_line)

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"```(?:json)?\s*```", "", cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    return cleaned_text, removed_any


def _normalize_stable_data_snapshot_conflicts(text: str) -> str:
    requested_date = ""
    for pattern in _STABLE_DATA_REQUEST_DATE_PATTERNS:
        match = pattern.search(text)
        if match:
            requested_date = match.group(1)
            break

    if not requested_date:
        return text

    def _replace_snapshot_line(match: re.Match[str]) -> str:
        snapshot_date = match.group(1)
        if snapshot_date == requested_date:
            return "The snapshot date of all valuation indicators should be based on the latest available trading day returned by the tool, and the current text date caliber still needs to be verified."
        return match.group(0)

    return _STABLE_DATA_SNAPSHOT_LINE_PATTERN.sub(_replace_snapshot_line, text)


def sanitize_report_artifacts(text: Any) -> str:
    raw_text = _as_text(text)
    if not raw_text:
        return ""

    normalized = _normalize_research_disclaimer(raw_text)
    normalized, _ = _strip_tool_call_artifacts(normalized)
    normalized = _normalize_stable_data_snapshot_conflicts(normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    return normalized


def is_low_signal_text(text: str) -> bool:
    normalized = _plain_text(text)
    if not normalized:
        return True
    if any(pattern.search(normalized) for pattern in _LOW_SIGNAL_PATTERNS):
        return True
    if normalized.startswith("-") and len(normalized) <= 14:
        return True
    return False


def _fragment_score(text: str) -> int:
    normalized = _plain_text(text)
    if not normalized:
        return -1

    score = min(len(normalized), 160)
    if is_low_signal_text(normalized):
        score -= 120
    if any(keyword in normalized for keyword in ("risk", "Profit", "growth", "pressure", "competition", "Valuation", "assets", "Liabilities", "catalysis", "Industry", "Macro", "demand", "income", "profit")):
        score += 60
    if normalized.startswith("-"):
        score -= 10
    return score


def sanitize_text_block(text: Any, fallback: str = "") -> str:
    raw_text = sanitize_report_artifacts(text)
    if not raw_text:
        return fallback

    lines: List[str] = []
    for chunk in re.split(r"\r?\n", raw_text):
        line = _plain_text(chunk)
        if not line or len(line) < 6:
            continue
        if _JSON_FIELD_PATTERN.match(line):
            continue
        if contains_actionable_content(line):
            continue
        if is_low_signal_text(line):
            continue
        lines.append(line)

    deduped: List[str] = []
    for line in lines:
        if line not in deduped:
            deduped.append(line)

    if not deduped:
        return fallback
    return "\n".join(deduped[:12])[:2500]


def contains_position_trigger_language(text: str) -> bool:
    if not text:
        return False
    normalized = _plain_text(text)
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _POSITION_TRIGGER_PATTERNS)


def _iter_position_review_fragments(text: Any) -> Iterable[str]:
    for fragment in _iter_review_fragments(text):
        yield fragment

    raw_text = _as_text(text)
    if not raw_text:
        return

    for chunk in re.split(r"\r?\n", raw_text):
        normalized = _plain_text(chunk)
        if not normalized:
            continue

        fragments = [
            fragment.strip()
            for fragment in _SENTENCE_SPLIT_PATTERN.split(normalized)
            if fragment.strip()
        ]
        if not fragments:
            fragments = [normalized]

        for fragment in fragments:
            if len(fragment) < 4:
                continue
            if _JSON_FIELD_PATTERN.match(fragment):
                continue
            if is_low_signal_text(fragment):
                continue
            if not contains_review_execution_guidance(fragment):
                continue

            simplified = _simplify_position_user_language(fragment)
            if not simplified or contains_review_execution_guidance(simplified):
                continue
            yield simplified


def sanitize_position_text_block(text: Any, fallback: str = "") -> str:
    deduped: List[str] = []
    for fragment in _iter_position_review_fragments(text):
        if contains_position_trigger_language(fragment):
            continue
        if any(pattern.match(fragment) for pattern in _POSITION_LABEL_ONLY_PATTERNS):
            continue
        if fragment not in deduped:
            deduped.append(fragment)

    if not deduped:
        return fallback
    return "；".join(deduped[:5])[:600]


def _normalize_position_list_items(value: Any, fallback: List[str], limit: int = 3) -> List[str]:
    raw_items: List[str] = []
    if isinstance(value, list):
        for item in value:
            text = _plain_text(item)
            if text:
                raw_items.append(text)
    elif value:
        raw_items.extend(_iter_position_review_fragments(value))

    cleaned_items: List[str] = []
    for item in raw_items:
        for fragment in _iter_position_clauses(item):
            cleaned = _clip_position_user_text(_simplify_position_user_language(fragment), 56)
            if not cleaned or contains_position_trigger_language(cleaned):
                continue
            if _is_low_signal_position_item(cleaned) or _looks_truncated_position_text(cleaned):
                continue
            if cleaned not in cleaned_items:
                cleaned_items.append(cleaned)
            if len(cleaned_items) >= limit:
                break
        if len(cleaned_items) >= limit:
            break

    if cleaned_items:
        return cleaned_items
    return fallback[:limit]


def _coerce_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _coerce_int(value: Any) -> int | None:
    number = _coerce_float(value)
    if number is None:
        return None
    return int(number)


def _extract_position_snapshot(result_data: Dict[str, Any], position_snapshot: Dict[str, Any] | None = None) -> Dict[str, Any]:
    if isinstance(position_snapshot, dict) and position_snapshot:
        return position_snapshot
    summary = result_data.get("summary")
    if isinstance(summary, dict):
        return summary
    return {}


def _simplify_position_user_language(text: str) -> str:
    normalized = _plain_text(text)
    if not normalized:
        return ""

    for old, new in _POSITION_PLAIN_LANGUAGE_REPLACEMENTS:
        normalized = normalized.replace(old, new)

    normalized = re.sub(
        r"Missing short-term goals(?:also)?untouched(?:and)?stop loss",
        "Short-term performance fell short of expectations, but there are currently no signs of further deterioration.",
        normalized,
    )
    normalized = re.sub(r"Missed target", "Performance fell short of expectations", normalized)
    normalized = re.sub(r"untouched(?:and)?stop loss", "There are no signs of further deterioration yet", normalized)

    normalized = re.sub(r"\s+", " ", normalized)
    normalized = normalized.replace("At this stage, there is no further deterioration in the short term,", "A more appropriate conclusion at this stage is to continue to observe: there will be no further deterioration in the short term;")
    normalized = normalized.replace("If there are still differences, we can only continue to observe for the time being.", "There are still differences, and we can only continue to observe for the time being.")
    normalized = normalized.replace("; price", "; stock price")
    normalized = normalized.replace("The current position is at", "At this stage")
    normalized = normalized.replace("；-", "；")
    normalized = normalized.replace("- ", "")
    return normalized.strip(" ；，。")


def _iter_position_clauses(text: Any) -> Iterable[str]:
    normalized = _plain_text(text)
    if not normalized:
        return

    for sentence in re.split(r"[。！？；]+", normalized):
        sentence = sentence.strip(" ；，。")
        if not sentence:
            continue

        comma_fragments = [
            fragment.strip(" ；，。")
            for fragment in re.split(r"[，、]+", sentence)
            if fragment.strip(" ；，。")
        ]
        if len(comma_fragments) >= 2:
            for fragment in comma_fragments:
                if len(fragment) >= 6:
                    yield fragment
            continue

        yield sentence


def _clip_position_user_text(text: str, max_len: int) -> str:
    normalized = _plain_text(text).strip(" ；，。:-")
    if not normalized:
        return ""
    if len(normalized) <= max_len:
        return normalized

    window = normalized[: max_len + 1]
    cut_at = max(window.rfind(marker) for marker in ("；", "。", "，", "、", "：", " "))
    if cut_at >= max(10, max_len // 2):
        clipped = window[:cut_at]
    else:
        clipped = window[:max_len]

    clipped = re.sub(r"(?:will|let|get|and|But|and|and|with|or|rule|Need|Wait|Yes)+$", "", clipped)
    return clipped.strip(" ；，。:-")


def _looks_truncated_position_text(text: str) -> bool:
    normalized = _plain_text(text).strip()
    if len(normalized) < 12:
        return False
    if re.search(r"[；，,:：\-/]$", normalized):
        return True
    return bool(re.search(r"(?:will|let|get|and|But|and|and|with|or|rule|Need|Wait|Yes)$", normalized))


def _is_low_signal_position_item(text: str) -> bool:
    normalized = _plain_text(text)
    return any(pattern.search(normalized) for pattern in _POSITION_GENERIC_ITEM_PATTERNS)


def _build_position_candidate_items(*sources: Any, limit: int = 3, max_len: int = 40) -> List[str]:
    items: List[str] = []
    for source in sources:
        for fragment in _iter_position_clauses(source):
            cleaned = _clip_position_user_text(_simplify_position_user_language(fragment), max_len)
            if len(cleaned) < 6:
                continue
            if contains_position_trigger_language(cleaned):
                continue
            if _is_low_signal_position_item(cleaned) or _looks_truncated_position_text(cleaned):
                continue
            if cleaned not in items:
                items.append(cleaned)
            if len(items) >= limit:
                return items
    return items


def _build_position_conclusion(*sources: Any) -> str:
    for source in sources:
        normalized = _clip_position_user_text(_simplify_position_user_language(source), 72)
        if normalized and not _looks_truncated_position_text(normalized) and (
            "Continue to observe" in normalized
            or "Performance fell short of expectations" in normalized
            or "further worsening the signal" in normalized
        ):
            return normalized

    clauses = _build_position_candidate_items(*sources, limit=2, max_len=32)
    if clauses:
        return _clip_position_user_text("；".join(clauses), 72)
    return "At this stage, it is more suitable to continue to observe and focus on confirming whether the original research logic still holds."


def _build_position_user_action_reason(
    result_data: Dict[str, Any],
    position_snapshot: Dict[str, Any] | None = None,
) -> tuple[str, str, Dict[str, Any]]:
    snapshot = _extract_position_snapshot(result_data, position_snapshot)
    raw_user_view = result_data.get("user_view") if isinstance(result_data.get("user_view"), dict) else {}
    analysis_summary = result_data.get("analysis_summary") if isinstance(result_data.get("analysis_summary"), dict) else {}
    neutral_advice = result_data.get("neutral_operation_advice") if isinstance(result_data.get("neutral_operation_advice"), dict) else {}
    if not neutral_advice and isinstance(result_data.get("neutral_operation_suggestion"), dict):
        neutral_advice = result_data.get("neutral_operation_suggestion")
    specific_plan = result_data.get("specific_plan") if isinstance(result_data.get("specific_plan"), dict) else {}
    cleaned_observation = _simplify_position_user_language(
        sanitize_position_text_block(
            raw_user_view.get("conclusion") or result_data.get("action_reason"),
            fallback="",
        )
    )
    cleaned_risk = sanitize_text_block(result_data.get("risk_assessment"), fallback="")
    cleaned_opportunity = sanitize_text_block(result_data.get("opportunity_assessment"), fallback="")

    current_price = _coerce_float(snapshot.get("current_price"))
    cost_price = _coerce_float(snapshot.get("cost_price"))
    unrealized_pnl_pct = _coerce_float(snapshot.get("unrealized_pnl_pct"))
    holding_days = _coerce_int(snapshot.get("holding_days"))

    snapshot_context_parts: List[str] = []
    if unrealized_pnl_pct is not None:
        abs_loss = abs(unrealized_pnl_pct)
        if unrealized_pnl_pct <= -30:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, It is already in a deep floating loss range.")
        elif unrealized_pnl_pct <= -15:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, It has deviated significantly from the original cost range.")
        elif unrealized_pnl_pct < 0:
            snapshot_context_parts.append(f"The current floating loss of this position is about{abs_loss:.2f}%, Still operating below costs.")
        elif unrealized_pnl_pct > 0:
            snapshot_context_parts.append(f"The current floating profit of this position is about{unrealized_pnl_pct:.2f}%, However, subsequent judgments still need to pay attention to whether the evidence continues.")

    if cost_price is not None and current_price is not None:
        snapshot_context_parts.append(f"Approximate cost price¥{cost_price:.2f}, Current price¥{current_price:.2f}. ")

    if holding_days is not None and holding_days >= 60:
        snapshot_context_parts.append(f"Holding time approx.{holding_days}Days later, priority should be given to confirming whether operations and risks have improved, rather than relying on short-term technical signals.")

    opening_parts = list(snapshot_context_parts)

    if cleaned_observation:
        opening_parts.append(cleaned_observation)
    else:
        opening_parts.append("At this stage, it is more appropriate to focus on confirming whether the research logic still holds, rather than directly interpreting short-term price fluctuations as the beginning of repair.")

    raw_position_context = _clip_position_user_text(
        _simplify_position_user_language(raw_user_view.get("position_context", "")),
        88,
    )
    if raw_position_context and not _looks_truncated_position_text(raw_position_context):
        position_context = raw_position_context
    else:
        position_context = _clip_position_user_text(" ".join(snapshot_context_parts[:3]).strip(), 96)

    conclusion = _build_position_conclusion(
        raw_user_view.get("conclusion"),
        cleaned_observation,
        analysis_summary.get("overall_view"),
        neutral_advice.get("core_judgment"),
    )

    key_points_fallback = _build_position_candidate_items(
        raw_user_view.get("conclusion"),
        cleaned_observation,
        analysis_summary.get("overall_view"),
        neutral_advice.get("core_judgment"),
        limit=3,
        max_len=38,
    ) or ["Current judgments still need to continue to check operating performance, risk changes and subsequent disclosures."]
    key_points = _normalize_position_list_items(
        raw_user_view.get("key_points") or analysis_summary.get("key_points") or neutral_advice.get("reasoning"),
        fallback=key_points_fallback,
    )
    risk_focus_fallback = _build_position_candidate_items(
        raw_user_view.get("risk_focus"),
        cleaned_risk,
        limit=3,
        max_len=42,
    ) or ["Please prioritize whether industry changes, company announcements, and position fluctuations continue to worsen."]
    risk_focus = _normalize_position_list_items(
        raw_user_view.get("risk_focus") or cleaned_risk,
        fallback=risk_focus_fallback,
    )
    watch_items_fallback = _build_position_candidate_items(
        raw_user_view.get("watch_items"),
        specific_plan.get("observation_factors"),
        neutral_advice.get("analysis_points"),
        cleaned_opportunity,
        limit=3,
        max_len=42,
    ) or ["The follow-up focus will be on operating quality, valuation changes and public catalysts that can change current judgments."]
    watch_items = _normalize_position_list_items(
        raw_user_view.get("watch_items") or specific_plan.get("observation_factors") or neutral_advice.get("analysis_points") or cleaned_opportunity,
        fallback=watch_items_fallback,
    )
    uncertainty_note = _clip_position_user_text(
        _simplify_position_user_language(raw_user_view.get("uncertainty_note", ""))
        or "The current conclusion is mainly based on disclosed information and needs to be verified in the future based on financial reports, announcements and industry changes.",
        72,
    )

    detailed_sections = [
        "### Current status",
        f"- {position_context}",
        f"- {conclusion}",
        "",
        "### core basis",
        *[f"- {item}" for item in key_points],
        "",
        "### Risk warning",
        *[f"- {item}" for item in risk_focus],
        "",
        "### Follow-up observation points",
        *[f"- {item}" for item in watch_items],
        "",
        "### uncertainty statement",
        f"- {uncertainty_note[:180]}",
    ]
    user_view = {
        "conclusion": conclusion[:80],
        "position_context": position_context[:96],
        "key_points": key_points,
        "risk_focus": risk_focus,
        "watch_items": watch_items,
        "uncertainty_note": uncertainty_note[:72],
    }
    compatibility_reason = _clip_position_user_text(f"{position_context} {conclusion}".strip(), 220)
    return compatibility_reason, "\n".join(detailed_sections).strip(), user_view


def _iter_review_fragments(text: Any) -> Iterable[str]:
    raw_text = _as_text(text)
    if not raw_text:
        return

    for chunk in re.split(r"\r?\n", raw_text):
        normalized = _plain_text(chunk)
        if not normalized:
            continue

        fragments = [
            fragment.strip()
            for fragment in _SENTENCE_SPLIT_PATTERN.split(normalized)
            if fragment.strip()
        ]
        if not fragments:
            fragments = [normalized]

        for fragment in fragments:
            if len(fragment) < 4:
                continue
            if _JSON_FIELD_PATTERN.match(fragment):
                continue
            if contains_review_execution_guidance(fragment):
                continue
            if is_low_signal_text(fragment):
                continue
            yield fragment


def sanitize_review_text_block(text: Any, fallback: str = "") -> str:
    deduped: List[str] = []
    for fragment in _iter_review_fragments(text):
        if fragment not in deduped:
            deduped.append(fragment)

    if not deduped:
        return fallback
    return "；".join(deduped[:6])[:1200]


def sanitize_review_detail_block(text: Any, fallback: str = "") -> str:
    raw_text = _as_text(text)
    if not raw_text:
        return fallback

    normalized = sanitize_report_artifacts(raw_text)
    if not normalized:
        return fallback

    cleaned_lines: List[str] = []

    for raw_line in normalized.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        plain = _plain_text(raw_line)
        if not plain:
            continue
        if _JSON_FIELD_PATTERN.match(plain):
            continue
        if contains_review_execution_guidance(plain):
            continue
        if is_low_signal_text(plain) and not stripped.startswith(("#", "-", "*")):
            continue

        cleaned_lines.append(raw_line.rstrip())

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

    if cleaned_text:
        return cleaned_text[:4000]

    return fallback


def sanitize_review_points(points: Any, fallback: Iterable[str] = ()) -> List[str]:
    cleaned_points: List[str] = []

    if isinstance(points, list):
        source_items = points
    elif points in (None, ""):
        source_items = []
    else:
        source_items = [points]

    for item in source_items:
        for fragment in _iter_review_fragments(item):
            if fragment not in cleaned_points:
                cleaned_points.append(fragment)
            if len(cleaned_points) >= 5:
                return cleaned_points

    for item in fallback:
        normalized = _plain_text(item)
        if normalized and normalized not in cleaned_points:
            cleaned_points.append(normalized)
        if len(cleaned_points) >= 5:
            break

    return cleaned_points[:5]


def sanitize_brief_points(points: Any) -> List[str]:
    cleaned_points: List[str] = []

    if not isinstance(points, list):
        return cleaned_points

    for item in points:
        normalized = _plain_text(_as_text(item))
        if len(normalized) < 2:
            continue
        if _JSON_FIELD_PATTERN.match(normalized):
            continue
        if contains_actionable_content(normalized):
            continue
        if is_low_signal_text(normalized):
            continue
        if normalized not in cleaned_points:
            cleaned_points.append(normalized[:120])
        if len(cleaned_points) >= 5:
            break

    return cleaned_points


def contains_inferential_evidence(text: str) -> bool:
    normalized = _plain_text(_as_text(text))
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in _INFERENTIAL_EVIDENCE_PATTERNS)


def normalize_research_brief_lists(
    core_evidence: Any,
    uncertainties: Any,
    invalidation_conditions: Any,
    watch_items: Any,
) -> Dict[str, List[str]]:
    cleaned_core_evidence = sanitize_brief_points(core_evidence)
    cleaned_uncertainties = sanitize_brief_points(uncertainties)
    cleaned_invalidation_conditions = sanitize_brief_points(invalidation_conditions)
    cleaned_watch_items = sanitize_brief_points(watch_items)

    normalized_core_evidence: List[str] = []
    demoted_inferential_items: List[str] = []

    for item in cleaned_core_evidence:
        if contains_inferential_evidence(item):
            demoted_inferential_items.append(item)
            continue
        normalized_core_evidence.append(item)

    for item in demoted_inferential_items:
        if item not in cleaned_uncertainties and len(cleaned_uncertainties) < 5:
            cleaned_uncertainties.append(item)
            continue
        if item not in cleaned_watch_items and len(cleaned_watch_items) < 5:
            cleaned_watch_items.append(item)

    return {
        "core_evidence": normalized_core_evidence[:5],
        "uncertainties": cleaned_uncertainties[:5],
        "invalidation_conditions": cleaned_invalidation_conditions[:5],
        "watch_items": cleaned_watch_items[:5],
    }


def sanitize_display_report_text(text: Any, fallback: str = "") -> str:
    raw_text = sanitize_report_artifacts(text)
    if not raw_text:
        return fallback

    cleaned_lines: List[str] = []
    in_disclaimer_block = False

    for raw_line in raw_text.splitlines():
        line = _normalize_display_line(raw_line.rstrip())
        normalized = _plain_text(line)

        if not normalized:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        if "Disclaimer" in normalized or normalized == RESEARCH_ONLY_DISCLAIMER:
            cleaned_lines.append(line)
            # Disclaimer text is retained in its entirety: actionable content filtering is skipped until the next markdown header
            in_disclaimer_block = True
            continue

        if in_disclaimer_block:
            if line.strip().startswith("#"):
                in_disclaimer_block = False
            else:
                cleaned_lines.append(line)
                continue

        if contains_actionable_content(normalized):
            continue
        if any(pattern.search(normalized) for pattern in _DISPLAY_REPORT_RISK_PATTERNS):
            continue

        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[0] == "":
        cleaned_lines.pop(0)
    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    cleaned_text = "\n".join(cleaned_lines)
    cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
    cleaned_text = _normalize_research_disclaimer(cleaned_text)

    if cleaned_text:
        return cleaned_text[:4000]

    return sanitize_text_block(raw_text, fallback=fallback)


def _build_position_appendix_sections(result_data: Dict[str, Any]) -> List[Dict[str, str]]:
    normalized_sections: List[Dict[str, str]] = []
    seen_keys: set[str] = set()

    raw_sections = result_data.get("appendix_sections")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not isinstance(item, dict):
                continue
            raw_title = str(item.get("title") or "").strip()
            key = str(item.get("key") or _POSITION_APPENDIX_TITLE_TO_KEY.get(raw_title) or "").strip()
            title = raw_title or dict(_POSITION_APPENDIX_SECTION_ORDER).get(key, "")
            content = sanitize_display_report_text(item.get("content"))
            if key and title and content and key not in seen_keys:
                normalized_sections.append({"key": key, "title": title, "content": content[:4000]})
                seen_keys.add(key)

    if normalized_sections:
        return normalized_sections

    section_content_by_key: Dict[str, str] = {}
    for key, _title in _POSITION_APPENDIX_SECTION_ORDER:
        cleaned_direct = sanitize_display_report_text(result_data.get(key))
        if cleaned_direct:
            section_content_by_key[key] = cleaned_direct

    raw_detailed_analysis = sanitize_report_artifacts(result_data.get("detailed_analysis"))
    if raw_detailed_analysis:
        current_key: str | None = None
        current_lines: List[str] = []

        def flush_current_section() -> None:
            nonlocal current_key, current_lines
            if not current_key:
                current_lines = []
                return
            cleaned = sanitize_display_report_text("\n".join(current_lines).strip())
            if cleaned and current_key not in section_content_by_key:
                section_content_by_key[current_key] = cleaned
            current_key = None
            current_lines = []

        for raw_line in raw_detailed_analysis.splitlines():
            stripped = raw_line.strip()
            heading_match = _POSITION_APPENDIX_HEADING_PATTERN.match(stripped)
            if heading_match:
                flush_current_section()
                current_key = _POSITION_APPENDIX_TITLE_TO_KEY.get(heading_match.group(1))
                continue
            if current_key:
                current_lines.append(raw_line)

        flush_current_section()

    for key, title in _POSITION_APPENDIX_SECTION_ORDER:
        content = section_content_by_key.get(key)
        if content:
            normalized_sections.append({"key": key, "title": title, "content": content[:4000]})

    return normalized_sections


def filter_analysis_reports(reports: Any) -> Dict[str, str]:
    if not isinstance(reports, dict):
        return {}

    filtered: Dict[str, str] = {}
    for key in SAFE_REPORT_KEYS:
        cleaned = sanitize_text_block(reports.get(key))
        if cleaned:
            filtered[key] = cleaned
    return filtered


def _iter_safe_fragments(reports: Dict[str, str], fallback_summary: str = "") -> Iterable[str]:
    if fallback_summary:
        cleaned_summary = sanitize_text_block(fallback_summary)
        if cleaned_summary:
            for fragment in _SENTENCE_SPLIT_PATTERN.split(cleaned_summary):
                sentence = fragment.strip()
                if sentence and not contains_actionable_content(sentence) and not is_low_signal_text(sentence):
                    yield sentence

    summary_priority = (
        "fundamentals_report",
        "market_report",
        "sector_report",
        "news_report",
        "sentiment_report",
        "index_report",
    )

    for key in summary_priority:
        content = sanitize_text_block(reports.get(key, ""))
        if not content:
            continue
        for fragment in _SENTENCE_SPLIT_PATTERN.split(content):
            sentence = fragment.strip()
            if sentence and not contains_actionable_content(sentence) and not is_low_signal_text(sentence):
                yield sentence


def build_research_summary(reports: Dict[str, str], fallback_summary: str = "") -> str:
    candidate_fragments: List[str] = []
    for fragment in _iter_safe_fragments(reports, fallback_summary):
        normalized = _plain_text(fragment)
        if normalized and normalized not in candidate_fragments:
            candidate_fragments.append(normalized)

    summary_parts = sorted(candidate_fragments, key=_fragment_score, reverse=True)[:3]

    if summary_parts:
        return "；".join(summary_parts)[:800]

    return "This result has been output in research-assisted mode. Please focus on basic data, risk factors and subsequent disclosure information."


def build_key_points(reports: Dict[str, str], key_points: Any, summary: str) -> List[str]:
    cleaned_points: List[str] = []
    if isinstance(key_points, list):
        for item in key_points:
            point = sanitize_text_block(item)
            if point and point not in cleaned_points and not is_low_signal_text(point):
                cleaned_points.append(point)

    if len(cleaned_points) >= 3:
        return cleaned_points[:5]

    for fragment in _iter_safe_fragments(reports, summary):
        if fragment not in cleaned_points and not is_low_signal_text(fragment):
            cleaned_points.append(fragment)
        if len(cleaned_points) >= 5:
            break

    return cleaned_points[:5]


def sanitize_analysis_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    reports = filter_analysis_reports(sanitized.get("reports") or {})
    summary = build_research_summary(reports, sanitized.get("summary", ""))

    sanitized["reports"] = reports
    sanitized["summary"] = summary
    sanitized["key_points"] = build_key_points(reports, sanitized.get("key_points"), summary)

    decision = sanitized.get("decision")
    normalized_action = ""
    if isinstance(decision, dict):
        sanitized_decision: Dict[str, Any] = {}
        action = decision.get("analysis_view") or decision.get("action")
        if isinstance(action, str) and action.strip():
            action_mapping = {
                "BUY": "optimistic",
                "SELL": "Prudence",
                "HOLD": "Neutral",
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "buy": "optimistic",
                "sell": "Prudence",
                "hold": "Neutral",
                "bullish": "optimistic",
                "Bearish": "Prudence",
                "optimistic": "optimistic",
                "Prudence": "Prudence",
                "Neutral": "Neutral",
            }
            normalized_action = action_mapping.get(action.strip(), action.strip())
            sanitized_decision["action"] = normalized_action
            sanitized_decision["analysis_view"] = normalized_action
        confidence = decision.get("confidence")
        if isinstance(confidence, (int, float)):
            sanitized_decision["confidence"] = confidence / 100 if confidence > 1 else confidence
        risk_score = decision.get("risk_score")
        if isinstance(risk_score, (int, float)):
            sanitized_decision["risk_score"] = risk_score / 100 if risk_score > 1 else risk_score
        reasoning = sanitize_text_block(decision.get("reasoning"), fallback=summary)
        if reasoning:
            sanitized_decision["reasoning"] = reasoning[:400]
        decision_summary = sanitize_text_block(decision.get("summary"))
        if decision_summary:
            sanitized_decision["summary"] = decision_summary[:240]
        risk_warning = sanitize_text_block(decision.get("risk_warning"))
        if risk_warning:
            sanitized_decision["risk_warning"] = risk_warning[:200]
        normalized_lists = normalize_research_brief_lists(
            decision.get("core_evidence"),
            decision.get("uncertainties"),
            decision.get("invalidation_conditions"),
            decision.get("watch_items"),
        )
        for field_name in ("core_evidence", "uncertainties", "invalidation_conditions", "watch_items"):
            cleaned_items = normalized_lists.get(field_name, [])
            if cleaned_items:
                sanitized_decision[field_name] = cleaned_items
        sanitized["decision"] = sanitized_decision

    recommendation_parts: List[str] = []
    if normalized_action:
        recommendation_parts.append(f"Research judgment:{normalized_action}")
    if summary:
        recommendation_parts.append(summary[:120])
    recommendation_parts.append("Please continue to pay attention to changes in evidence, risk factors and subsequent disclosures in conjunction with the detailed report.")
    sanitized["recommendation"] = "；".join(part for part in recommendation_parts if part)[:240] or GENERIC_RESEARCH_RECOMMENDATION

    return sanitized


def sanitize_position_analysis_payload(
    result_data: Dict[str, Any],
    position_snapshot: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    appendix_sections = _build_position_appendix_sections(sanitized)
    action_reason, user_detailed_analysis, user_view = _build_position_user_action_reason(sanitized, position_snapshot)
    summary = action_reason or sanitize_position_text_block(
        sanitized.get("summary") or sanitized.get("action_reason") or sanitized.get("detailed_analysis"),
        fallback="This position research has been converted into research observation, please make independent judgment based on your own strategy.",
    )

    sanitized["action"] = "hold"
    sanitized["action_reason"] = action_reason or "Currently, only research conclusions, risk warnings and observation points are retained, and no execution trading suggestions are provided."
    sanitized["price_targets"] = {}
    sanitized["suggested_quantity"] = None
    sanitized["suggested_amount"] = None
    sanitized["risk_assessment"] = sanitize_text_block(
        sanitized.get("risk_assessment"),
        fallback="Please focus on position fluctuations, industry changes and announcement risks.",
    )
    sanitized["opportunity_assessment"] = sanitize_text_block(
        sanitized.get("opportunity_assessment"),
        fallback="Please continue to track operating quality, valuation changes and potential catalytic events.",
    )
    sanitized["detailed_analysis"] = user_detailed_analysis
    sanitized["user_view"] = user_view
    sanitized["appendix_sections"] = appendix_sections
    sanitized["summary"] = summary
    sanitized["recommendation"] = GENERIC_POSITION_RECOMMENDATION

    confidence = sanitized.get("confidence")
    if isinstance(confidence, (int, float)):
        sanitized["confidence"] = max(0.0, min(100.0, float(confidence)))

    return sanitized


def sanitize_trade_review_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    sanitized["summary"] = sanitize_review_text_block(
        sanitized.get("summary"),
        fallback=GENERIC_REVIEW_SUMMARY,
    )
    sanitized["strengths"] = sanitize_review_points(sanitized.get("strengths"))
    sanitized["weaknesses"] = sanitize_review_points(sanitized.get("weaknesses"))
    sanitized["suggestions"] = sanitize_review_points(
        sanitized.get("suggestions"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["timing_analysis"] = sanitize_review_detail_block(
        sanitized.get("timing_analysis"),
        fallback="Please focus on reviewing whether the basis for entry and exit is sufficient, rather than giving new trading instructions.",
    )
    sanitized["position_analysis"] = sanitize_review_detail_block(
        sanitized.get("position_analysis"),
        fallback="Please focus on reviewing the basis for position management and risk exposure, and do not provide specific position adjustment plans.",
    )
    sanitized["emotion_analysis"] = sanitize_review_detail_block(
        sanitized.get("emotion_analysis"),
        fallback="Please focus on reviewing the issues of emotional control and discipline enforcement.",
    )
    sanitized["attribution_analysis"] = sanitize_review_detail_block(
        sanitized.get("attribution_analysis"),
        fallback="Please focus on reviewing the evidence attribution of the sources of gains and losses.",
    )
    sanitized["plan_adherence"] = sanitize_review_text_block(sanitized.get("plan_adherence"))
    sanitized["plan_deviation"] = sanitize_review_text_block(sanitized.get("plan_deviation"))
    sanitized.pop("optimal_pnl", None)
    sanitized.pop("missed_profit", None)
    sanitized.pop("avoided_loss", None)

    return sanitized


def sanitize_periodic_review_payload(result_data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(result_data, dict) or not result_data:
        return result_data

    sanitized = dict(result_data)
    sanitized["summary"] = sanitize_review_text_block(
        sanitized.get("summary"),
        fallback=GENERIC_REVIEW_SUMMARY,
    )
    sanitized["trading_style"] = sanitize_review_text_block(
        sanitized.get("trading_style"),
        fallback="Please conduct a phased review from the perspective of style stability, discipline execution and research preparation adequacy.",
    )
    sanitized["common_mistakes"] = sanitize_review_points(sanitized.get("common_mistakes"))
    sanitized["improvement_areas"] = sanitize_review_points(
        sanitized.get("improvement_areas"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["action_plan"] = sanitize_review_points(
        sanitized.get("action_plan"),
        fallback=GENERIC_REVIEW_IMPROVEMENTS,
    )
    sanitized["best_trade"] = sanitize_review_text_block(sanitized.get("best_trade"))
    sanitized["worst_trade"] = sanitize_review_text_block(sanitized.get("worst_trade"))

    return sanitized