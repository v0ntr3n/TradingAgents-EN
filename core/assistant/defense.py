"""Intelligent assistant reply quality defense line (A11 is collected from app/services/intelligent_assistant_service.py).

This module is assisted by four lines of defense and digital traceability**sole source of truth** (Physical relocation, logic does not change):
1. _has_fabricated_tool_json   Fabrication tool JSON result hard interception
2. _has_fabricated_tool_refs   Forgery tool call traces
3. _has_unsourced_numbers      The tool is not adjusted but contains a lot of specific numbers
4. _has_untraced_risky_numbers Tools tweaked but mixed with high-risk numbers that can t be traced

service layer pass `from core.assistant.defense import ...` Reuse these names,
ReplyGate This module is also called uniformly——Replies from any path pass through the same set of defenses.

Design documents:docs/05-design/v3.0/assistant-quality-architecture-refactor.md §3.3
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)


# ── Regular and retry instructions for fabricated/untraced detection ───────────────────────────────────────────
# Match fake traces of tool calls in responses (e.g."Data source:get_xxx_tool"or"📌 Data source: XXX tool") 
_FABRICATED_TOOL_REF_RE = re.compile(
    r"(Data source[:: ]\s*(get_|fetch_)[a-z_]+|📌\s*Data source[:: ].*Tools)",
    re.IGNORECASE,
)
# Match the specific numbers that appear in the reply (100 million yuan / 10,000 yuan / yuan / kilogram, etc.), used to detect the situation where the tool is not adjusted but the data is given
_SPECIFIC_NUMBER_RE = re.compile(
    r"[\d,]+\.?\d*\s*(billion|Ten thousand yuan|Yuan|Kilogram|vehicle|head|%|pct|Quantile|x|times)"
)
# match"Tool name(parameters) → { JSON result }"Mode: All real tools return Markdown text,
# The tool results packaged into JSON objects in the reply must be structured fields fabricated by LLM (such as post_count: 127) 
_FABRICATED_TOOL_JSON_RE = re.compile(
    r"(get_|fetch_|trigger_|set_)[a-z0-9_]+\s*\([^)\n]{0,80}\)[^{\n]{0,60}\{[^{}\n]{5,500}\}",
    re.IGNORECASE,
)
# "The tool is not tuned but the response contains a large number of numbers"Automatic error correction and retry instructions after interception (retry at most 1 time)
_UNSOURCED_RETRY_PROMPT = (
    " [System Verification Feedback] Your reply just now contains a lot of specific numbers, but you did not use any tools in this conversation."
    "These numbers cannot be traced back to their source. They are training memory padding and have been intercepted by the system.\n"
    "Please re-answer the user s question, requiring:\n"
    "1. You must first call relevant tools to obtain real data (for industry/sector questions, use get_sector_daily or search_sector."
    "For individual stock questions, use get_stock_market_data_unified / get_technical_indicators,"
    "Use get_web_search for the latest industry trends);\n"
    "2. Only answer based on real data returned by the tool, and indicate the source and date when quoting figures;\n"
    "3. If the tool does not return relevant data, please clearly state that the data is missing and do not use any specific numbers."
)

# "Tools have been adjusted, but high-risk numbers cannot be traced back to their origins"Automatic error correction and retry instructions after interception (retry at most 1 time)
_UNTRACED_RETRY_PROMPT_TEMPLATE = (
    " [System verification feedback] The following specific numbers were quoted in your reply just now:{numbers}, "
    "However, these numbers are neither in the results returned by the current round of tools, nor in the results of historical tools or factual memory, and cannot be traced back to their origins."
    "It is suspected to come from training memory and has been intercepted by the system.\n"
    "Please re-answer the user s question, requiring:\n"
    "1. Only the numbers that appear in the tool return are quoted; if the calculation results based on the tool numbers (such as range increase and decrease,"
    "year-on-year change), the calculation formula and the basis figures must be listed in the reply (for example: from X to Y, the increase=(Y-X)/X) , "
    "And the calculation must be correct;\n"
    "2. When new data is needed, call the tool first (for industry/sector questions, use get_sector_daily or "
    "analyze_sector_by_name, For individual stock questions, use get_stock_market_data_unified."
    "Use get_web_search for the latest industry trends);\n"
    "3. Data not covered by the tool will be changed to a qualitative description or a clear explanation of missing data, and fabricating specific numbers is prohibited."
)


def _build_untraced_interception(untraced_detail: str) -> str:
    """structure"High-risk numbers cannot be traced"Interception copy (reveal after failed retry)."""
    return (
        "Sorry, I quoted some specific numbers in my reply that are not available in the tools or search results."
        f" (Such as {untraced_detail}) , Such numbers may come from outdated memory rather than real-time data,"
        "Continuing to present it will mislead your judgment, so the entire section has been blocked.\n\n"
        "Common reasons: The search results only have titles/links/abstracts and do not contain specific values."
        " (For example, industry cost data are mostly in the text of paid research reports and cannot be captured by search engine summaries).\n"
        "You can:\n"
        "• Change to more specific keywords and let me search again (such as\"Muyuan Shares July Cost Announcement\") \n"
        "• Let me quote the source link I searched for and let you manually view the original text.\n"
        "• Only let me analyze real data that has been returned by the tool\n"
    )


# ── The fourth line of defense: high-risk digital traceability verification ─────────────────────────────────────────────
# Extract high-risk numbers with financial units in responses (long units are prioritized, avoid"Yuan/kg"Be"Yuan"truncate;
# Covers both Chinese and English unit writing: Yuan/kg and Yuan/kg are the same unit)
_RISKY_NUMBER_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*(Yuan/[kK][gG]|Yuan/kg|Yuan/ton|Yuan/jin|billion|Ten thousand yuan|Thousands of hands|Quantile|pct|%|times|Yuan|hand)"
)
# The extraction tool returns all numbers in the text (with financial units or bare numbers, such as the JSON field value 0.37 / 15764.6)
_TOOL_NUMBER_RE = re.compile(
    r"(\d[\d,]*\.?\d*)\s*(Yuan/[kK][gG]|Yuan/kg|Yuan/ton|Yuan/jin|billion|Ten thousand yuan|Thousands of hands|Quantile|pct|%|times|Yuan|hand)?"
)
# Amount type unit → normalized to"billion"conversion factor
_AMOUNT_UNIT_FACTOR = {"billion": 1.0, "Ten thousand yuan": 1e-4}
# Reverse the amount of naked numbers on the tool side: When the tool returns naked numbers without units (such as transaction volume, scale),
# When LLM responds with amount units such as "100 million yuan/10,000 yuan", the reverse calculation is based on the following common units
#  (Normalized to 100 million yuan), if they match, the traceability is successful.
# Prioritize the use of large units (100 million yuan, 10,000 yuan) in order to avoid accidentally bumping into naked price figures when placing large numbers in small units.
_BARE_AMOUNT_GUESS_FACTORS = [
    ("billion", 1.0),
    ("Ten thousand yuan", 1e-4),
    ("Yuan", 1e-8),
]
# Transaction volume naked digital inversion (hand ↔ Thousands of hands)
_BARE_VOLUME_GUESS_FACTORS = [
    ("Thousands of hands", 1e-4),  # 1 hand = 0.0001 Thousands of hands
    ("hand", 1.0),
]
# weight price unit → normalized to"Yuan/kg"conversion factor (multiply this factor=Converted into yuan/kg price).
# price per kilogram = Price per catty × 2 (1 Kilogram=2 catties); price per kilogram = price per ton ÷ 1000 (1 tons=1000 kg).
# LLM The yuan/kg returned by the tool is often converted into yuan/jin (such as 10.87 yuan/kg → 5.44 Yuan/jin),
# It is a legal conversion and not a fabrication.
_WEIGHT_UNIT_FACTOR = {"Yuan/kg": 1.0, "Yuan/jin": 2.0, "Yuan/ton": 0.001}
# Match Tolerance (the upper limit of the relative error between the tool value and the recovery value; 1% covers conventional rounding,
# Also avoid cross-semantic mismatches——such as fabricating"15.8 Yuan/kg"hit staking holding_ratio 15.54)
_TRACE_TOLERANCE = 0.01
# Special tolerances for percentage figures (increases and decreases, rates, etc. are prone to errors due to rounding or cumulative calculations)
# For example, the tool returns 0.17%, LLM says"approx.0.2%"It's reasonable, not fabricated
_TRACE_PCT_TOLERANCE = 0.05
# List of percentage units
_PCT_UNITS = {"%", "pct", "Quantile"}
# Non-traceable high-risk numbers up to this amount → Trigger interception (no longer adjust LLM to retry, change to local fuzzing)
# The threshold should not be too low: it is reasonable for LLM to do simple addition/average/rounding on tool returns,
# Such as"management fee 0.15%+Escrow fee 0.05%=0.20%", "Cumulative rise and fall in the past 5 days 1.93%"Wait
_UNTRACED_NUMBER_LIMIT = 6


def _normalize_unit(unit: str) -> str:
    """Unit aliases are unified: Yuan/kg and Yuan/kg are regarded as the same unit."""
    u = (unit or "").lower()
    return u.replace("/kg", "/Kilogram").replace("kg", "Kilogram")


def _parse_number(text: str) -> Optional[float]:
    """'1,771.97' → 1771.97; Returns None on failure."""
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _extract_risky_numbers(text: str, pattern: "re.Pattern") -> list:
    """extract from text (numerical value, unit) For lists, the units should be lowercase."""
    out = []
    for m in pattern.finditer(text or ""):
        val = _parse_number(m.group(1))
        if val is None:
            continue
        unit = (m.group(2) or "").lower() if pattern.groups >= 2 else ""
        out.append((val, unit))
    return out


def _number_matches(value: float, unit: str, candidates: list) -> bool:
    """judge (numerical value, unit) Whether the origin can be traced in the candidate set (the number returned by the tool).

    Matching rules:
    - Amount category (100 million yuan/10,000 yuan): must belong to the same amount category, and will be matched after normalization to 100 million yuan
       (Such as 157.646 million ↔ 1.58 billion; 157.646 million ≠ 157.6 billion, to prevent 100 times conversion errors)
    - Weight price category (yuan/kg, yuan/jin, yuan/ton): normalized to yuan/kg and then matched
       (Such as 5.44 yuan/jin ↔ 10.87 Yuan/kg, legal unit conversion does not count as fabrication)
    - Non-amount categories (%/yuan/kg/kg/multiple/quantile/naked number): differences in unit writing are directly matched by numerical value (1% tolerance)
    - Don t do it ×100 Percentage conversion: The tool returns 0.37, which is 0.37%, and the reply is 37%, which is regarded as non-traceable.
    - Bottom line: bare numbers on the tool side (no unit) but when the reply contains the amount/trading volume unit, reverse matching based on common units
       (If the tool returns 5,435.33 million yuan → LLM Saying 5.435 billion yuan is a reasonable conversion)
    """
    tol = _TRACE_TOLERANCE
    unit = _normalize_unit(unit)
    value_is_amount = unit in _AMOUNT_UNIT_FACTOR
    value_is_volume = unit in ("Thousands of hands", "hand")
    value_is_pct = unit in _PCT_UNITS
    for cand_val, cand_unit_raw in candidates:
        cand_unit = _normalize_unit(cand_unit_raw)
        cand_is_amount = cand_unit in _AMOUNT_UNIT_FACTOR
        cand_is_bare = cand_unit == ""
        cand_is_pct = cand_unit in _PCT_UNITS
        # Percentage category: use special tolerance (it is reasonable if the rounding/cumulative calculation error is large)
        if value_is_pct and cand_is_pct:
            if cand_val == 0 and value == 0:
                return True
            ref = max(abs(cand_val), abs(value), 1e-9)
            if abs(value - cand_val) <= _TRACE_PCT_TOLERANCE * ref:
                return True
            continue
        # A percentage on one side and a bare number on the other. → Percentage tolerance is also used (the raw number of the tool is often the percentage value)
        if value_is_pct and cand_is_bare:
            ref = max(abs(cand_val), abs(value), 1e-9)
            if abs(value - cand_val) <= _TRACE_PCT_TOLERANCE * ref:
                return True
        # 1) Both sides are units of amount → Direct comparison after normalizing to 100 million yuan
        if value_is_amount and cand_is_amount:
            v1 = value * _AMOUNT_UNIT_FACTOR[unit]
            v2 = cand_val * _AMOUNT_UNIT_FACTOR[cand_unit]
            if abs(v1 - v2) <= tol * max(abs(v2), 1e-9):
                return True
            continue
        # Candidate is amount but reply is not → Skip to avoid mismatching price/percentage etc. to amount
        if cand_is_amount and not value_is_amount:
            continue
        # 2) Weight price unit: Normalized to yuan/kg for comparison (jin↔Kilogram ×2, tons↔Kilogram ×1000) 
        if unit in _WEIGHT_UNIT_FACTOR and cand_unit in _WEIGHT_UNIT_FACTOR:
            v1 = value * _WEIGHT_UNIT_FACTOR[unit]
            v2 = cand_val * _WEIGHT_UNIT_FACTOR[cand_unit]
            if abs(v1 - v2) <= tol * max(abs(v2), 1e-9):
                return True
        # 3) Non-amount categories: Match if the values are equal (differences in unit writing are tolerated)
        if abs(value - cand_val) <= tol * max(abs(cand_val), 1e-9):
            return True
        # 4) Bottom line: There are bare numbers on the tool side, and the reply contains the amount/trading volume unit. → Backcast by common units
        if cand_is_bare and cand_val > 0:
            if value_is_amount:
                v1 = value * _AMOUNT_UNIT_FACTOR[unit]
                for _, factor in _BARE_AMOUNT_GUESS_FACTORS:
                    v2 = cand_val * factor
                    if v2 <= 0:
                        continue
                    if abs(v1 - v2) <= tol * max(abs(v2), 1e-9):
                        return True
            elif value_is_volume:
                # normalized to"hand"Compare again
                v1 = value * (10000 if unit == "Thousands of hands" else 1)
                for _, factor in _BARE_VOLUME_GUESS_FACTORS:
                    # factor Yes candidate value(In factor_unit) → Conversion factor for hands
                    # Normalization is obtained:cand_val * factor
                    v2 = cand_val * factor
                    if v2 <= 0:
                        continue
                    if abs(v1 - v2) <= tol * max(abs(v2), 1e-9):
                        return True
    return False


def _find_closest_candidate(value: float, unit: str, candidates: list) -> Optional[tuple]:
    """Find the closest value in a tool candidate set (and a statement of the derivation relationship) for an untraceable number.

    Return (cand_val, cand_unit, relation_desc) or None.
    relation_desc Describe the derivation relationship, such as"Rounding", "Cumulative/difference estimates", "Unit conversion"wait.
    """
    unit = _normalize_unit(unit)
    tol = _TRACE_TOLERANCE
    pct_tol = _TRACE_PCT_TOLERANCE
    value_is_amount = unit in _AMOUNT_UNIT_FACTOR
    value_is_volume = unit in ("Thousands of hands", "hand")
    value_is_pct = unit in _PCT_UNITS

    best = None  # (relative_diff, cand_val, cand_unit, relation)

    for cand_val, cand_unit_raw in candidates:
        cand_unit = _normalize_unit(cand_unit_raw)
        cand_is_amount = cand_unit in _AMOUNT_UNIT_FACTOR
        cand_is_bare = cand_unit == ""
        cand_is_pct = cand_unit in _PCT_UNITS

        v1 = value
        v2 = cand_val
        relation = None

        # Amount type (both sides are amount units)
        if value_is_amount and cand_is_amount:
            v1 = value * _AMOUNT_UNIT_FACTOR[unit]
            v2 = cand_val * _AMOUNT_UNIT_FACTOR[cand_unit]
            relation = f"{cand_val}{cand_unit} (unit conversion)"
        # Percent category
        elif value_is_pct and cand_is_pct:
            relation = f"{cand_val}{cand_unit} (Rounding/approximation)"
        elif value_is_pct and cand_is_bare:
            relation = f"{cand_val} (Rounding/approximation)"
        # Amount + Naked numbers (reverse push)
        elif value_is_amount and cand_is_bare:
            best_guess = None
            for guess_unit, factor in _BARE_AMOUNT_GUESS_FACTORS:
                v2_guess = cand_val * factor
                if v2_guess <= 0:
                    continue
                rel_diff = abs(value * _AMOUNT_UNIT_FACTOR[unit] - v2_guess) \
                    / max(abs(v2_guess), 1e-9)
                if rel_diff < 0.5:  # If it is relaxed to within 50%, it will be considered as a reference.
                    if best_guess is None or rel_diff < best_guess[0]:
                        best_guess = (rel_diff, cand_val, guess_unit,
                                      f"{cand_val}Yuan ≈ {cand_val * factor:.2f}100 million yuan (estimated amount)")
            if best_guess:
                rel_diff, cv, cu, desc = best_guess
                if best is None or rel_diff < best[0]:
                    best = (rel_diff, cv, cu, desc)
            continue
        # Volume + Naked numbers
        elif value_is_volume and cand_is_bare:
            best_guess = None
            for guess_unit, factor in _BARE_VOLUME_GUESS_FACTORS:
                v1_hand = value * (10000 if unit == "Thousands of hands" else 1)
                v2_hand = cand_val * factor
                if v2_hand <= 0:
                    continue
                rel_diff = abs(v1_hand - v2_hand) / max(abs(v2_hand), 1e-9)
                if rel_diff < 0.5:
                    desc = f"{cand_val}hand ≈ {cand_val * factor / 10000:.2f}10,000 lots (estimated trading volume)" \
                        if guess_unit == "Thousands of hands" \
                        else f"{cand_val}Hand (raw data)"
                    if best_guess is None or rel_diff < best_guess[0]:
                        best_guess = (rel_diff, cand_val, guess_unit, desc)
            if best_guess:
                rel_diff, cv, cu, desc = best_guess
                if best is None or rel_diff < best[0]:
                    best = (rel_diff, cv, cu, desc)
            continue
        # Same unit (price/multiple, etc.)
        elif unit == cand_unit or (cand_is_bare and not value_is_amount):
            relation = f"{cand_val}{cand_unit} (Approximately)"
        else:
            continue

        if v2 == 0 and v1 == 0:
            rel_diff = 0.0
        else:
            ref = max(abs(v2), abs(v1), 1e-9)
            rel_diff = abs(v1 - v2) / ref

        # Skip those that are too different (>100% Basically it doesn't matter)
        if rel_diff > 1.0:
            continue
        if rel_diff < (pct_tol if value_is_pct else tol):
            relation = relation or f"{cand_val}{cand_unit}"
        if best is None or rel_diff < best[0]:
            best = (rel_diff, cand_val, cand_unit, relation or f"{cand_val}{cand_unit}")

    if best is None:
        return None
    return (best[1], best[2], best[3])


def _get_untraced_risky_numbers(
    reply: str,
    tool_results: Optional[list],
    user_message: str = "",
    history_tool_contents: Optional[list] = None,
    return_candidates: bool = False,
):
    """Extract high-risk numbers in responses that cannot be traced back to the original text (or user message) returned by the tool.

    Args:
        tool_results: This round of tool return (collector collection)
        user_message: User messages (quoting numbers given by users does not count as fabrication)
        history_tool_contents: in session history role=tool The content of the message (when there are multiple rounds of dialogue,
            The real data quoted from the previous round of tools can also be traced and should not be misjudged)
        return_candidates: True return when (untraced, candidates) For log troubleshooting

    Returns:
        not traceable "numerical value+unit" String list (used for log and threshold judgment).
    """
    if not reply:
        return ([], []) if return_candidates else []
    # The tool returns all numbers (including naked numbers) in the original text as a credible candidate set
    candidates: list = []
    for item in (tool_results or []):
        content = item.get("content") or ""
        if not content or item.get("is_error"):
            continue
        candidates.extend(_extract_risky_numbers(content, _TOOL_NUMBER_RE))
    # Numbers returned by the tool in the session history are equally trustworthy (multiple rounds of references)
    for content in (history_tool_contents or []):
        if content:
            candidates.extend(_extract_risky_numbers(content, _TOOL_NUMBER_RE))
    # Numbers appearing in user messages are also considered credible (numbers given by users quoted by the assistant are not considered fabricated)
    user_numbers = _extract_risky_numbers(user_message or "", _TOOL_NUMBER_RE)
    candidates.extend(user_numbers)

    untraced = []
    for m in _RISKY_NUMBER_RE.finditer(reply):
        val = _parse_number(m.group(1))
        unit = (m.group(2) or "").lower()
        if val is None:
            continue
        # Exclusion: Noise such as years (1900-2099), small integer serial numbers in percentages, etc. are eliminated by the threshold.
        if 1900 <= val <= 2099 and val == int(val):
            continue
        if _number_matches(val, unit, candidates):
            continue
        untraced.append(f"{m.group(1)}{m.group(2)}")
    if return_candidates:
        return untraced, candidates
    return untraced


def _build_data_transparency_note(
    reply: str,
    tool_results: list,
    user_message: str,
    history_tool_contents: list,
) -> Optional[str]:
    """Generate a data description postscript: transparently label the derived/estimated numbers for users to make their own judgments.

    Instead of hard interception, LLM expression values, tool original values, and possible derivation relationships are listed.
    """
    untraced, candidates = _get_untraced_risky_numbers(
        reply, tool_results, user_message, history_tool_contents, return_candidates=True)
    if not untraced:
        return None

    lines = []
    for num_str in untraced[:8]:
        # Parse values and units
        m = _RISKY_NUMBER_RE.match(num_str)
        if not m:
            continue
        try:
            val = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        unit = m.group(2) or ""
        closest = _find_closest_candidate(val, unit, candidates)
        if closest:
            _, _, relation = closest
            lines.append(f"- **{num_str}**: Tool reference data {relation}, The above are estimated/derived values, please refer to them with caution")
        else:
            lines.append(f"- **{num_str}**: The corresponding data was not found in the tool return, please verify")

    if not lines:
        return None

    return (
        "\n\n---\n"
        "📌 **Data description**\n"
        "The following values are derived or estimated based on the original data of the tool (possibly after rounding, cumulative calculation, unit conversion, etc.),"
        "The original tool data is also listed, please make your own judgment:\n"
        + "\n".join(lines)
    )


# ── four main lines of defense ────────────────────────────────────────────────────────────────

def _has_fabricated_tool_json(reply: str) -> bool:
    """Check if the tool results are fabricated as JSON objects in the reply.

    The actual return of all tools in the system is Markdown text (output_shape=markdown) , 
    will never return {"sentiment_score": 0.32, "post_count": 127} This type of JSON.
    If it appears in the reply"Tool name(parameters) ... { json }"mode, indicating that LLM constructed its own
    Structured fake data returned by the tool —— Hard interception.
    """
    if not reply:
        return False
    m = _FABRICATED_TOOL_JSON_RE.search(reply)
    if m:
        logger.warning("[Smart Assistant] Fabricated tool JSON results detected: %.120s", m.group(0))
        return True
    return False


def _has_fabricated_tool_refs(reply: str, tools_used: list) -> bool:
    """Detect whether traces of tool calls are forged in responses.

    Judgment criteria: appeared in the reply"Data source:get_xxx_tool"and other words,
    But tools_used is empty or does not contain the corresponding tool name.
    """
    if not reply:
        return False
    matches = _FABRICATED_TOOL_REF_RE.findall(reply)
    if not matches:
        return False
    # There are traces of tool references but no actual calls to any tools → forgery
    if not tools_used:
        return True
    # If there are tool reference traces, check whether the referenced tool name is in tools_used
    # Extract tool name from reply
    tool_names_in_reply = set()
    for m in re.finditer(r"(get_|fetch_)[a-z_]+", reply, re.IGNORECASE):
        tool_names_in_reply.add(m.group(0).lower())
    tools_used_lower = {t.lower() for t in tools_used}
    # If none of the referenced tool names are in the actual call list → forgery
    if tool_names_in_reply and not tool_names_in_reply.intersection(tools_used_lower):
        return True
    return False


def _has_unsourced_numbers(reply: str, tools_used: list) -> bool:
    """Detect if the response contains a large number of specific numbers without calling any data tools.

    Used to block LLM from not adjusting the tool but fabricating accurate financial/sales figures in responses.
    """
    if not reply or tools_used:
        return False
    # Count the number of specific numbers in responses
    numbers = _SPECIFIC_NUMBER_RE.findall(reply)
    # More than 5 specific numbers without adjusting any tools → Most likely fabricated
    return len(numbers) > 5


def _has_untraced_risky_numbers(
    reply: str,
    tool_results: Optional[list],
    tools_used: list,
    user_message: str = "",
    history_tool_contents: Optional[list] = None,
) -> bool:
    """The fourth line of defense: The tool was called, but the response contained a large number of high-risk numbers that could not be traced.

    Scenario: LLM does call the tool (the first three lines of defense pass), but uses training memory to make up for it
    Numbers not returned by the tool (e.g."Industry cost line 15.8 yuan/kg""PE 75% percentile in the past 5 years") , 
    Or the tool figures are incorrectly converted (0.37 is said to be 37%, 157.646 million is said to be 15.76 billion).
    """
    if not reply or not tools_used:
        return False
    untraced, candidates = _get_untraced_risky_numbers(
        reply, tool_results, user_message, history_tool_contents, return_candidates=True
    )
    if len(untraced) >= _UNTRACED_NUMBER_LIMIT:
        # Comes with candidate set summary for easy troubleshooting"The number is in the tool return but does not match"misjudgment (such as differences in unit aliases)
        cand_preview = [f"{v}{u}" for v, u in candidates[:30]]
        logger.warning(
            "[Smart Assistant] %d untraceable high-risk numbers detected: %s | tool candidate set(%d a, before 30): %s",
            len(untraced), untraced[:10], len(candidates), cand_preview,
        )
        return True
    return False
