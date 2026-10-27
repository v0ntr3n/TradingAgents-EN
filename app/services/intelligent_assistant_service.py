"""
Intelligent assistant service - Agent autonomous orchestration mode

Tools that support the ReAct mode can be called autonomously for event-driven analysis, exploratory query and other scenarios.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from bson import ObjectId

# Intelligent assistant overall timeout (LLM + Multiple rounds of tool calls).
# The design is aligned with mainstream Agents (ChatGPT/Manus, etc.): the agent cycle does not have a short global timeout,
# Rely on "single step timeout (tool tier 15/180s)+ Round limit (max_tool_rounds=8) +
# Streaming progress feedback + User manual stop" controls the duration; the global timeout is just a safety net to prevent hangups.
# Actual Measurement: Inference Model (Long Thinking)+ 277 Tools schema + Long session history, first round LLM thoughts
# Up to 4 minutes, 300s will be cut off just after the tool is executed (2026-09-15 revenue forecast export case).
ASSISTANT_TIMEOUT_SECONDS = int(os.environ.get("ASSISTANT_TIMEOUT_SECONDS", "900"))
# Additional timeout margin added when heavy tools (Agent calls, etc.) are used in the conversation
ASSISTANT_HEAVY_TOOL_EXTRA_SECONDS = 120

# Maximum number of session history items (per user)
ASSISTANT_CONVERSATION_LIMIT = 100
ASSISTANT_DEFAULT_THREAD_ID = "default"
ASSISTANT_MAX_CONTEXT_MESSAGES = 10
ASSISTANT_MAX_REPORT_REFS = 12
ASSISTANT_REPORT_INBOX_TITLE = "报告收纳"

from core.tools import get_tool_registry, tool_metadata_list_to_openai
from core.tools.context import set_current_assistant_thread_id, set_current_user_id
from core.llm import UnifiedLLMClient
from core.llm.models import LLMConfig, LLMProvider, Message, MessageRole, ToolCall, ToolResult

# A11 Intelligent assistant quality architecture: recovery quality defense line (fabricated detection/digital traceability) and contract-based sole export.
# The defense implementation has been integrated into core.assistant.defense (single source of truth), where import is unified and reused;
# All path replies are exported through ReplyGate, evidence is carried through Evidence/ReplyCandidate, and data_refs is implemented.
from core.assistant import (
    EVIDENCE_MEMORY,
    EVIDENCE_SEARCH,
    EVIDENCE_TOOL,
    AssistantRequest,
    Evidence,
    PathRegistry,
    PRIORITY_DATA_PRECHECK,
    PRIORITY_FAST_SEARCH,
    PRIORITY_HITL,
    PRIORITY_LLM_UNAVAILABLE,
    PRIORITY_MAIN_LLM,
    PRIORITY_UNSUPPORTED_ASSET,
    ReplyCandidate,
    ReplyGate,
    ROUTE_DATA_PRECHECK,
    ROUTE_ERROR,
    ROUTE_FAST_SEARCH,
    ROUTE_HITL,
    ROUTE_LLM_UNAVAILABLE,
    ROUTE_MAIN_LLM,
    ROUTE_TIMEOUT,
    ROUTE_TYPE_PASSTHROUGH,
    ROUTE_TYPE_ANSWER,
    ROUTE_UNSUPPORTED_ASSET,
    detect_unsupported_asset,
    extract_a_share_code,
    extract_data_refs,
    quality_metrics,
    stock_directory,
)
from core.assistant.reply_gate import build_fallback_candidate
from core.assistant.defense import (
    _SPECIFIC_NUMBER_RE,
    _UNSOURCED_RETRY_PROMPT,
    _UNTRACED_RETRY_PROMPT_TEMPLATE,
    _build_data_transparency_note,
    _get_untraced_risky_numbers,
    _has_fabricated_tool_json,
    _has_fabricated_tool_refs,
    _has_unsourced_numbers,
    _has_untraced_risky_numbers,
)

logger = logging.getLogger(__name__)

_MEMORY_FACT_KEYWORDS = [
    "结论", "营收", "收入", "净利润", "扣非", "毛利率", "现金流", "分红", "股息率", "估值",
    "预期", "超预期", "低于预期", "价格战", "成本", "销量", "增长", "下滑", "风险", "压力",
    "支撑", "阻力", "走势", "震荡", "偏弱", "偏强", "回调", "反弹", "逻辑", "原因",
]

_NUMBER_ONLY_REPLY_RE = re.compile(r"^\s*([1-9]\d?)\s*[\.、\)）]?\s*$")
_NUMBERED_OPTION_LINE_RE = re.compile(r"^\s*(\d{1,2})\s*[\.、\)）]\s*(.+?)\s*$")


def _extract_memory_subject(user_msg: str, assistant_msg: str) -> str:
    title_match = re.search(r"##\s*[📌✅⚠️🔍💡]*\s*([A-Za-z0-9\u4e00-\u9fff]{2,20})(?:[（(][^\n]{0,20}[)）])?(?:——|\-|：|:)", assistant_msg or "")
    if title_match:
        return title_match.group(1).strip()

    user_match = re.search(r"([A-Za-z0-9\u4e00-\u9fff]{2,20})(?:stocks|trend|performance|performance|dividend|How to see|why|how)", user_msg or "")
    if user_match:
        return user_match.group(1).strip()

    return ""


def _clean_memory_line(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^#+\s*", "", cleaned)
    cleaned = re.sub(r"^[>\-*\d\.\s✅⚠️📌🔍💡]+", "", cleaned)
    cleaned = re.sub(r"\*+", "", cleaned)
    cleaned = re.sub(r"`+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip(" |：:-")


def _build_fallback_memory_facts(user_msg: str, assistant_msg: str, limit: int = 5) -> List[str]:
    subject = _extract_memory_subject(user_msg, assistant_msg)
    candidates: List[str] = []

    for raw_line in (assistant_msg or "").splitlines():
        line = _clean_memory_line(raw_line)
        if not line or len(line) < 10:
            continue
        if line.startswith("|") or set(line) <= {"-", "|", ":", " "}:
            continue
        if "数据来源" in line:
            continue
        if any(keyword in line for keyword in _MEMORY_FACT_KEYWORDS):
            if subject and subject not in line and len(line) < 70:
                line = f"{subject}：{line}"
            candidates.append(line[:120])

    seen = set()
    facts: List[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        facts.append(item)
        if len(facts) >= limit:
            break
    return facts


# Data related keywords——Used to determine whether the user's question involves stock data query
_STOCK_DATA_KEYWORDS = [
    "财报", "利润", "营收", "收入", "净利润", "毛利率", "现金流", "资产", "负债",
    "估值", "市盈率", "市净率", "pe", "pb", "ps",
    "销量", "产量", "出栏", "交付",
    "价格", "股价", "行情", "涨跌", "涨幅", "跌幅",
    "入手", "买入", "卖出", "加仓", "减仓", "持有", "清仓", "值得", "能不能买", "该不该",
    "分析", "研究", "怎么样", "如何", "技术面", "基本面", "基本面",
]


def _extract_stock_code(user_message: str) -> Optional[str]:
    """Extract the 6-digit A-share stock code from user messages (regular fact source: core.assistant.lexicon)."""
    return extract_a_share_code(user_message)


async def _resolve_stock_name_to_code(user_message: str, db=None) -> Optional[str]:
    """Attempts to match a stock name from a user message and return a stock symbol.

    Source of fact: core.assistant.lexicon.stock_directory (stock_basic_info full
    Name→Code directory + TTL cache), replacing the historically hard-coded common names + Check the regex library on every request.
    db Parameters take precedence; try if not passed get_mongo_db() (will fail in some contexts).
    """
    if not user_message:
        return None
    try:
        if db is None:
            from app.core.database import get_mongo_db
            db = get_mongo_db()
        return await stock_directory.resolve_symbol(user_message, db)
    except Exception as e:
        logger.warning("[Smart Assistant] Stock name resolution failed: %s", e)
        return None


async def _check_stock_data_sync(symbol: str, db=None) -> dict:
    """Check the data synchronization status of a single stock and return {has_historical, has_financial, has_basic, ...}. 

    Directly query the actual data collection (consistent with the front-end data inspection interface):
    - Basic data: stock_basic_info (press symbol)
    - Historical Quotes: stock_daily_quotes (press symbol/code)
    - financial data: stock_financial_data (press symbol)
    """
    try:
        if db is None:
            from app.core.database import get_mongo_db
            db = get_mongo_db()

        normalized = str(symbol).strip().upper()
        if "." in normalized:
            normalized = normalized.split(".", 1)[0]

        # Basic data
        basic_doc = await db["stock_basic_info"].find_one(
            {"symbol": normalized}, {"symbol": 1, "name": 1}
        )

        # Historical quotes (stock_daily_quotes, compatible with both symbol/code fields)
        hist_count = await db["stock_daily_quotes"].count_documents({"symbol": normalized})
        if hist_count == 0:
            hist_count = await db["stock_daily_quotes"].count_documents({"code": normalized})
        hist_latest = await db["stock_daily_quotes"].find_one(
            {"symbol": normalized}, sort=[("trade_date", -1)]
        ) or await db["stock_daily_quotes"].find_one(
            {"code": normalized}, sort=[("trade_date", -1)]
        )
        hist_last_date = None
        if hist_latest:
            d = hist_latest.get("trade_date") or hist_latest.get("date")
            hist_last_date = str(d)[:10] if d else None

        # financial data
        fin_count = await db["stock_financial_data"].count_documents({"symbol": normalized})

        return {
            "has_historical": hist_count > 0,
            "has_financial": fin_count > 0,
            "has_basic": basic_doc is not None,
            "hist_records": hist_count,
            "fin_records": fin_count,
            "hist_last_date": hist_last_date,
            "stock_name": basic_doc.get("name") if basic_doc else None,
            "symbol": normalized,
        }
    except Exception as e:
        logger.warning("[Smart Assistant] Checking stock data sync status failed(%s): %s", symbol, e)
        return {"error": str(e)}


# The reply quality defense line (fabricated detection rules/digital traceability/retry instructions/transparency notes) has been incorporated into
# core.assistant.defense (A11, single source of truth), see import at the top of the file for symbols.


def _retry_message(role: str, content: str) -> Message:
    """Construct a retry feedback message.

    Note: achat requires messages to be core.llm.models.Message objects (pydantic),
    Direct append dict will trigger 'dict' object has no attribute 'role'. 
    """
    return Message(role=MessageRole(role), content=content)


# The four main lines of defense (fabricated JSON/forged references/untraceable numbers/high-risk digital traceability) have been incorporated into
# core.assistant.defense (A11) , Called uniformly by ReplyGate.


def _extract_history_tool_contents(messages: List[Any]) -> List[str]:
    """Extract traceable and credible text from the conversation history (for multi-round tracing).

    Covers two types of content:
    1. Historical tool messages (the tool returns the original text);
    2. History assistant replies——These responses are all verified through the four lines of defense before being dropped into the database.
       It is a verified and trusted text. LLM refers to numbers from its previous round of responses (e.g. derived values,
       The conclusion of the last round of search) should not be judged as fabrication.
    """
    contents = []
    for m in (messages or []):
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None)
        if content is None and isinstance(m, dict):
            content = m.get("content")
        if role in ("tool", "assistant") and content:
            contents.append(str(content))
    return contents


def _recent_user_context(messages: List[Any], max_messages: int = 6) -> str:
    """Extract the spliced text of recent user messages in the session (used to extract related stocks when saving memory).

    Industry memory (such as"Pig breeding cost") The subject does not contain the stock name, but the memory of the
    Session context usually has (such as"Is Muyuan shares worth buying?") ——Establish accordingly
    stocks↔Industry memory associations.
    """
    texts = []
    for m in (messages or []):
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else None)
        content = getattr(m, "content", None)
        if content is None and isinstance(m, dict):
            content = m.get("content")
        if role == "user" and content:
            texts.append(str(content))
    return " ".join(texts[-max_messages:])[-2000:]


# ── Factual memory layer (with time tags, real data obtained by reusing tools across sessions)──────────────────────
# Design points:
# 1. Establish memory only for successful results of online tools such as web_search/fetch_url (including source, valuable across sessions);
#    Local data tools (financial/markets) do not build memory——Every time the database is queried, the latest value is obtained, so caching is meaningless.
# 2. Each memory strip fetched_at (acquisition time)+ category (data category)+ valid_until (expiration time),
#    During retrieval, only unexpired memories are returned; expired data is not injected and will be overwritten by the new round of tool results.
# 3. The memory injected into prompt is added to the traceability candidate set: the assistant's reference to the memory number will not be mistakenly blocked by the fourth line of defense.
_MEMORY_FACTS_COLLECTION = "assistant_memory_facts"
# An online tool that can be saved as factual memory (results include external world data and have reuse value across sessions)
# Note: tool_id must be consistent with core/tools registration name (previously written by mistake web_search/fetch_url
# As a result, it was never hit, and now it is corrected to the real ID; the old name is retained for compatibility)
_MEMORY_FACT_TOOLS = {
    "search_recent_information",  # Internet search (real tool ID)
    "get_stock_news_unified",     # Individual stock news aggregation
    "web_search",                 # Compatibility reserved
    "fetch_url",                  # Compatibility reserved
}
# Category rules:(Category name, keyword list, Valid days), order is priority
_FACT_CATEGORY_RULES = [
    ("realtime_quote", ["价格", "行情", "均价", "现价", "股价", "涨跌", "实时", "点位"], 3),
    ("industry_metric", ["成本", "存栏", "产能", "出栏", "销量", "市场份额", "行业"], 30),
    ("company_financial", ["财报", "营收", "净利", "季报", "年报", "毛利", "现金流", "业绩"], 90),
    ("company_static", ["上市日期", "主营业务", "公司简介", "注册地", "成立时间", "发展历程"], 365),
]
_FACT_DEFAULT_VALID_DAYS = 7
# Fact sentence extraction: reply/tool in original text"Contains numbers + Hit these keywords"Only short sentences will be stored in memory
_FACT_SENTENCE_KEYWORDS = [
    "销量", "交付", "产量", "出栏", "存栏", "产能",
    "成本", "价格", "均价", "毛利", "利润", "营收", "收入", "净利", "亏损", "盈利",
    "同比", "环比", "增长", "下滑", "下降", "上升", "上涨", "下跌", "回落", "涨幅", "跌幅",
    "占比", "份额", "市占率", "分红", "股息", "估值", "市盈率",
    "调研", "评级", "公告",
    "亿元", "万元", "元/", "公斤", "千克", "kg", "吨", "斤", "万辆", "万头",
]
# The maximum number of facts stored in each round / the maximum length of a single fact
_MEMORY_FACT_MAX_PER_TURN = 6
_MEMORY_FACT_MAX_CHARS = 150
# The upper limit of the number of items returned by the search/the upper limit of the length of a single injection
_MEMORY_RECALL_TOP_K = 3
_MEMORY_INJECT_MAX_CHARS = 1500
# Topic matching: Bigram intersections reaching this number are considered hits.
_MEMORY_MATCH_THRESHOLD = 2


def _classify_fact_category(text: str) -> str:
    """Determine the data category based on text keywords (determine the memory validity period)."""
    t = text or ""
    for category, keywords, _days in _FACT_CATEGORY_RULES:
        if any(k in t for k in keywords):
            return category
    return "default"


def _fact_valid_days(category: str) -> int:
    for cat, _kw, days in _FACT_CATEGORY_RULES:
        if cat == category:
            return days
    return _FACT_DEFAULT_VALID_DAYS


def _extract_match_tokens(text: str) -> set:
    """Extract text matching tokens: Chinese bigram + English words + Number string."""
    if not text:
        return set()
    tokens = set()
    # Chinese bigram ("Pig breeding" → {pig, Pig raising, Breeding}) 
    chinese_runs = re.findall(r"[\u4e00-\u9fa5]+", text)
    for run in chinese_runs:
        for i in range(len(run) - 1):
            tokens.add(run[i : i + 2])
    # English word / number string
    for w in re.findall(r"[A-Za-z]{2,}|\d{4,}", text):
        tokens.add(w.lower())
    return tokens


def _extract_symbol_hint(text: str) -> Optional[str]:
    """Extract the 6-digit A-share code from the text (memory associated stock, optional)."""
    m = re.search(r"\b(\d{6})\b", text or "")
    return m.group(1) if m else None


# Extraction of related entities: stock name (common suffixes such as XX shares/XX group) and 6-digit code.
# Purpose: Industry memory (such as"Pig breeding cost") When saving, record the stocks involved in the current session
#  (Such as"Muyuan shares") , Follow up by asking any questions about the stock (such as"Has Muhara rebounded?") Can bring out the industry background
_RELATED_NAME_RE = re.compile(
    r"[\u4e00-\u9fa5]{2,4}(?:shares|Group|Technology|biology|energy|animal husbandry|Agriculture|bank|securities|Pharmaceutical industry|Heavy industry|electrician|car|Medicine)"
)


def _extract_related_terms(
    *texts: str, name_map: Optional[Dict[str, str]] = None
) -> List[str]:
    """Extract related subjects (stock names) from multiple paragraphs of text+code), up to 8.

    name_map: Stock name→Code mapping (if None, only regular names are extracted).
    After passing in the mapping,"Thalys"Such company names without suffix can also get associated codes (such as 601127),
    Ensure that industry/stock memory storage and retrieval results are consistent on both sides.
    """
    terms = set()
    _connectives = "With and and contrast with or,,. ??; ;: : "
    joined = " ".join(t for t in texts if t)
    for t in texts:
        if not t:
            continue
        for m in _RELATED_NAME_RE.finditer(t):
            name = m.group(0).lstrip(_connectives)
            if len(name) >= 4:  # At least 2 words company name+2 word suffix
                terms.add(name)
        for code in re.findall(r"\b\d{6}\b", t):
            terms.add(code)
    for name, sym in (name_map or {}).items():
        if name in joined:
            terms.add(sym)
    return sorted(terms)[:8]


# Memory link stock name→Code mapping uses core.assistant.lexicon.stock_directory
#  (full amount + TTL cache), the private cache of this module is no longer maintained. Semantic bridge description: industry memory
#  (Such as"Complete cost of pig breeding") Although the stock name is not included, the session context when saving (the user is in Liamu Yuan)
# Association can be established, and the stock will be hit when searching——solve"When asking about individual stocks, I want to remember the industry background."question


def _clean_fact_line(text: str) -> str:
    """Clean candidate fact sentences: only remove list symbols/asterisks/backticks, leaving the beginning of the number intact.

    Note: Do not reuse _clean_memory_line——It will strip the first digits of the line (putting"1-7 Monthly cumulative sales"
    mistakenly cleared to"Monthly cumulative sales") , Destroy the fact that sales/production etc. begin with a number.
    """
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^[>\-\*\s✅⚠️📌🔍💡]+", "", cleaned)
    cleaned = re.sub(r"\*+", "", cleaned)
    cleaned = re.sub(r"`+", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_fact_sentences(text: str, max_facts: int = _MEMORY_FACT_MAX_PER_TURN) -> List[str]:
    """extract from text"Contains numbers + hit fact keywords"Short sentences (used for memorization, no additional adjustment of LLM).

    Applicable scenarios (by priority):
    1. Assistant s final reply——Four digital traceability lines have been passed. The number in the sentence can be traced back to the results of this round of tools.
       Drop it directly into the database as a fact (e.g."Cyrus new energy sales in July 2026 24,229 vehicle") ; 
    2. Tools return to the original text——A search result snippet is often a fact in itself.

    Rules: Cut sentences according to periods/semicolons/line breaks, keep sentences that contain numbers and hit factual keywords, and clean and remove duplicates.
    """
    if not text:
        return []
    facts: List[str] = []
    seen = set()
    for raw in re.split(r"[。！？；;\n]+", text):
        sent = _clean_fact_line(raw)
        if len(sent) < 8:
            continue
        if sent.startswith("|"):  # table row
            continue
        if any(t in sent for t in ("数据来源", "免责声明", "不构成投资建议", "以上内容")):
            continue
        if not re.search(r"\d", sent):
            continue  # There is no fact without numbers
        if not any(k in sent for k in _FACT_SENTENCE_KEYWORDS):
            continue
        sent = sent[:_MEMORY_FACT_MAX_CHARS]
        if sent in seen:
            continue
        seen.add(sent)
        facts.append(sent)
        if len(facts) >= max_facts:
            break
    return facts


def _fact_topic(
    fact: str, user_message: str, name_map: Optional[Dict[str, str]] = None
) -> str:
    """Generate a memory topic (subject) for a single fact+concept), such as"Cyrus Sales". 

    Subject sources (by priority):
    1. Unambiguous body in user messages (regex matching"Stock/Trend/Performance…"etc. suffix);
    2. The longest hit name in the stock name map (e.g."Thalys"It can also be recognized without suffix, take the longest
       avoid"Lis"substring mismatch);
    3. factual text"XX Shares/XX Automobile"Class name.
    The concept is the first core word hit by the fact (sales/cost/price…) . 
    Search with"Subject+concept"The bigram hit can be recalled.
    """
    subject = _extract_memory_subject(user_message, fact)
    if not subject and name_map:
        text = f"{user_message or ''} {fact or ''}"
        name_hits = [name for name in name_map if len(name) >= 2 and name in text]
        if name_hits:
            subject = max(name_hits, key=len)
    if not subject:
        m = _RELATED_NAME_RE.search(fact or "")
        if m:
            subject = m.group(0)
    concept = next((k for k in _FACT_SENTENCE_KEYWORDS if k in (fact or "")), "")
    parts = [p for p in (subject, concept) if p]
    if not parts:
        return ""
    return " ".join(parts)[:60]


async def _persist_memory_facts(
    db,
    tool_results: List[Dict[str, Any]],
    user_message: str,
    thread_id: str,
    assistant_reply: str = "",
    related_context: str = "",
) -> int:
    """Put behind this round of online tools"extract facts"Save as memory (no longer save tool to return to full text).

    Sources of facts (in order of priority):
    1. Assistant s final reply——Passed the digital traceability defense line, among which"Contains numbers+fact keywords"short sentences
       i.e. credible facts (e.g."Cyrus new energy sales in July 2026 24,229 vehicle") ; 
    2. Get the bottom line: Extract short sentences in the same format from the original text returned by the tool (the search result summary itself is often
       a fact such as"Muyuan was surveyed by 11 institutions: the full cost in 2025 is 12 yuan/kg") . 

    Compared to the old implementation (returning the tool to full text storage content[:8000]) : 
    - every memory≤150 Characters, small size, no pressure for retrieval and injection;
    - The number exists directly in the content, and can be entered into the traceability candidate set (memory_trusted_contents) after changing the session and recalling it;
    - Topic button"Subject+concept"Generate (such as"Cyrus Sales") , bigram Recall on hit.

    Args:
        assistant_reply: The final reply of this round of assistants (passed the digital traceability defense line).
        related_context: Session recent context (such as the splicing of several recent user messages),
            Used to withdraw associated stock deposits related_terms——Industry facts thereby influence the stock
            was recalled in a follow-up question.

    Returns:
        Number of items saved (0 means no facts can be saved).
    """
    saved = 0
    try:
        name_map = await stock_directory.get_name_map(db)
        related_terms = _extract_related_terms(user_message, related_context, name_map=name_map)
        facts = _extract_fact_sentences(assistant_reply or "")
        if not facts:
            # There is no fact that can be extracted from the reply (such as a pure conversational reply), and it will be extracted from the original text of the tool.
            for item in (tool_results or []):
                if item.get("tool") not in _MEMORY_FACT_TOOLS or item.get("is_error"):
                    continue
                facts.extend(_extract_fact_sentences(item.get("content") or ""))
                if len(facts) >= _MEMORY_FACT_MAX_PER_TURN:
                    break
        if not facts:
            return 0
        tools_used_str = ",".join(
            sorted({str(i.get("tool", "")) for i in (tool_results or []) if i.get("tool")})
        )
        now = datetime.now()
        for fact in facts[:_MEMORY_FACT_MAX_PER_TURN]:
            topic = _fact_topic(fact, user_message, name_map)
            if not topic:
                continue
            category = _classify_fact_category(fact)
            valid_until = now + timedelta(days=_fact_valid_days(category))
            doc = {
                "topic": topic,
                "symbol": _extract_symbol_hint(fact),
                "related_terms": related_terms,
                "tool_id": tools_used_str,
                "content": fact,
                "fetched_at": now.isoformat(timespec="seconds"),
                "category": category,
                "valid_until": valid_until.isoformat(timespec="seconds"),
                "thread_id": thread_id,
            }
            # Same factual sentences (topic+content) upsert Refresh, different facts are separated into strips
            await db[_MEMORY_FACTS_COLLECTION].update_one(
                {"topic": topic, "content": fact}, {"$set": doc}, upsert=True
            )
            saved += 1
            logger.info(
                "[Smart Assistant·memory] Saved facts: topic=%.40s category=%s fact=%.50s",
                topic, category, fact,
            )
    except Exception as e:
        logger.warning("[Smart Assistant·memory] Failed to save fact memory (does not affect reply): %s", e)
    return saved


async def _recall_memory_facts(
    db,
    user_message: str,
    current_thread_id: str,
) -> List[Dict[str, Any]]:
    """Retrieve unexpired fact memories that match the current question (excluding those saved by this session).

    Matching strategy (dual channel):
    1. Topic/Content Matching: User Messages and Memories"Topic+factual content"Intersection of word elements (mainly bigram)
       ——factual sentences (≤150 word) overall participation in matching, ask"Cyrus sales in July"Can hit directly
       "Cyrus new energy sales in July 2026 24,229 vehicle"This type of tacked-on fact;
    2. Related subject matching: stocks mentioned in user messages (such as"Muyuan shares"/"002714", Contains name→code
       mapping) intersects with the related_terms recorded when the memory was saved——Industry memory (such as
       "Pig breeding cost") This can be used to analyze individual stock issues (such as"Has Muhara rebounded?") was recalled.
    """
    try:
        now_iso = datetime.now().isoformat(timespec="seconds")
        user_tokens = _extract_match_tokens(user_message or "")
        name_map = await stock_directory.get_name_map(db)
        user_terms = set(_extract_related_terms(user_message, name_map=name_map))
        if not user_tokens and not user_terms:
            return []
        cursor = (
            db[_MEMORY_FACTS_COLLECTION]
            .find({"valid_until": {"$gte": now_iso}})
            .sort("fetched_at", -1)
            .limit(100)
        )
        scored = []
        async for doc in cursor:
            if current_thread_id and doc.get("thread_id") == current_thread_id:
                continue  # This data already exists in the context of this session, so there is no need to re-inject it.
            match_text = f"{doc.get('topic') or ''} {doc.get('content') or ''}"
            topic_tokens = _extract_match_tokens(match_text)
            overlap = user_tokens & topic_tokens
            related_hit = bool(
                user_terms & set(doc.get("related_terms") or [])
            )
            if len(overlap) >= _MEMORY_MATCH_THRESHOLD or related_hit:
                # Topic direct hits have a higher weight than associated subject hits
                scored.append((len(overlap) * 10 + (1 if related_hit else 0), doc))
        scored.sort(key=lambda x: -x[0])
        recalled = [doc for _score, doc in scored[:_MEMORY_RECALL_TOP_K]]
        if recalled:
            logger.info(
                "[Smart Assistant·memory] Hit %d fact memories: %s",
                len(recalled),
                [d.get("topic", "")[:30] for d in recalled],
            )
        return recalled
    except Exception as e:
        logger.warning("[Smart Assistant·memory] Failed to retrieve fact memory (downgraded to no memory): %s", e)
        return []


def _build_memory_injection(recalled: List[Dict[str, Any]]) -> str:
    """Construct the memory of the hit as a block of text injected into prompt."""
    if not recalled:
        return ""
    blocks = [
        " [Memory of historical facts] The following is the real data obtained through the tool in the previous session (passed timeliness verification),"
        "Can be quoted directly, but the date of data collection must be marked when quoting; if the user is asking about the latest situation,"
        "The time of data collection should be proactively stated and re-verification recommended."
    ]
    for i, doc in enumerate(recalled, 1):
        fetched = str(doc.get("fetched_at", ""))[:16].replace("T", " ")
        topic = doc.get("topic", "")
        content = str(doc.get("content", ""))[:_MEMORY_INJECT_MAX_CHARS]
        blocks.append(
            f"--- 记忆 {i} | 采集于 {fetched} | 来源 {doc.get('tool_id', '')} | 主题：{topic} ---\n{content}"
        )
    return "\n\n".join(blocks)


def _should_force_tool_retry(user_message: str) -> bool:
    """Determine whether it belongs to Tools should be called first personal data inquiry request."""
    text = (user_message or "").strip().lower()
    if not text:
        return False

    # personal data+Operation query intention (plan/position/review/task/report, etc.)
    personal_markers = ["我的", "我", "当前", "现在"]
    domain_markers = [
        "交易计划", "投资计划", "计划", "持仓", "仓位", "复盘", "报告", "分析任务", "任务状态",
        "股票关注列表", "定时分析", "提醒", "schedule", "watchlist", "position", "review", "plan",
    ]
    query_markers = ["查看", "列出", "查询", "获取", "多少", "有没有", "是什么", "详情", "状态"]

    has_personal = any(k in text for k in personal_markers)
    has_domain = any(k in text for k in domain_markers)
    has_query = any(k in text for k in query_markers)

    market_markers = [
        "大盘", "指数", "上证", "深证", "创业板", "沪深300", "中证", "点位", "收盘", "开盘",
        "成交额", "量能", "涨跌家数", "北向", "南向", "主力资金", "技术面", "技术指标",
        "macd", "rsi", "kdj", "boll", "布林", "均线", "ma", "ema", "超买", "超卖",
        "背离", "支撑", "阻力", "回调", "反弹", "突破", "压力位", "自然周期",
    ]
    recency_markers = ["最新", "当前", "现在", "今日", "今天", "近期", "最近", "截至目前", "今年", "本周", "本月"]

    has_market = any(k in text for k in market_markers)
    has_recency = any(k in text for k in recency_markers)

    # Meet at least: personal+field, or field+Query, or Market+Recently, or stocks+data
    # Stock data issues: stock code/name + Data-related vocabulary (e.g."Is Muyuan shares worth buying?") 
    import re
    has_stock_code = bool(re.search(r"(00|30|60|68)\d{4}", text))
    has_stock_name = any(k in text for k in ["股份", "集团", "科技", "新能", "汽车", "银行", "证券", "保险", "能源", "牧原", "赛力斯", "比亚迪", "宁德"])
    stock_data_markers = [
        "财报", "利润", "营收", "收入", "净利润", "毛利率", "现金流", "资产", "负债",
        "估值", "市盈率", "市净率", "pe", "pb", "ps",
        "销量", "产量", "出栏", "交付",
        "价格", "股价", "行情", "涨跌", "涨幅", "跌幅",
        "入手", "买入", "卖出", "加仓", "减仓", "持有", "清仓", "值得", "能不能买", "该不该",
        "分析", "研究", "怎么样", "如何",
    ]
    has_stock_data = any(k in text for k in stock_data_markers)
    stock_data_query = (has_stock_code or has_stock_name) and has_stock_data

    return (has_personal and has_domain) or (has_domain and has_query) or (has_market and has_recency) or stock_data_query


async def _record_assistant_token_usage(
    resp_obj: Any,
    session_id: str,
    analysis_type: str = "assistant",
) -> None:
    """Record the token usage of LLM calls (failure does not affect the main process)."""
    try:
        from app.services.usage_statistics_service import usage_statistics_service
        await usage_statistics_service.record_llm_usage(
            response=resp_obj,
            session_id=session_id,
            analysis_type=analysis_type,
        )
    except Exception as e:
        logger.warning(f"Record token usage failure: {e}")


# =============================================================================
# User mnemonic tool: LLM allows users to express"please remember""Please help me write it down"Actively register when waiting for intention
# Design document reference:docs/05-design/v3.0/unified-memory-layer-mem0.md §15.5 P0-1
# =============================================================================

REMEMBER_THIS_TOOL_NAME = "remember_this"


def _build_remember_this_tool_def() -> Dict[str, Any]:
    """structure `remember_this` Definition of OpenAI Function Calling"""
    return {
        "type": "function",
        "function": {
            "name": REMEMBER_THIS_TOOL_NAME,
            "description": (
                "This tool is called when the user clearly expresses intentions such as please remember , please write it down for me , I hope this preference will be followed in the future , etc."
                "Write this preference/fact into the user s long-term memory (user_preference)."
                "After calling, please inform the user that it has been noted and then continue to complete the original task."
                "Abuse prohibited: only if the user**Explicit expression requires memorization**When called; preferences mentioned casually by the user should not be written."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "Factual text that needs to be remembered (one sentence, containing enough context, such as User preference dividend rate >3%high-dividend blue-chip stocks and avoid growth stocks with high price-to-earnings ratios )",
                    },
                    "category": {
                        "type": "string",
                        "description": "Preference type: investment_style (investment style) / risk_tolerance (risk preference) / industry_preference (industry preference) / trading_discipline (trading discipline)/ other",
                        "enum": [
                            "investment_style",
                            "risk_tolerance",
                            "industry_preference",
                            "trading_discipline",
                            "other",
                        ],
                    },
                },
                "required": ["content"],
            },
        },
    }


def _make_remember_this_callable(db, user_id: str):
    """Generated binding db + user_id The asynchronous implementation of remember_this."""

    async def _remember_this(content: str, category: str = "other") -> str:
        if not user_id:
            return "Memory failure: The user is not associated with the current session."
        text = (content or "").strip()
        if not text:
            return "Memory failed: content is empty."
        try:
            from core.memory.service import get_memory_service
            from core.memory.models import MemoryScope
            svc = get_memory_service(db)
            result = await svc.store(
                [{"role": "user", "content": text}],
                user_id=user_id,
                agent_id="assistant",
                scope=MemoryScope.USER_PREFERENCE,
                metadata={
                    "source": "user_explicit_remember",
                    "category": (category or "other").strip().lower(),
                },
                infer=False,  # The user has made it clear that no further LLM extraction is required
            )
            if not result.success:
                logger.warning(f"[Smart Assistant] remember_this Write failed: {result.error}")
                return f"Memory failure:{result.error or 'Memory layer is not available'}"
            logger.info(f"[Smart Assistant] remember_this has been written: user={user_id} category={category}")
            return f"Note down:{text[:60]}{'...' if len(text) > 60 else ''}. This preference will be automatically referenced in the next conversation."
        except Exception as e:
            logger.warning(f"[Smart Assistant] remember_this Abnormal: {e}")
            return f"Memory failure:{e}"

    return _remember_this


def _should_use_recent_search(user_message: str) -> bool:
    """Determine whether it is a fact-confirming question that should be searched first in the near future."""
    text = (user_message or "").strip().lower()
    if not text:
        return False

    recency_markers = [
        "截至目前", "截至现在", "最新", "近期", "最近", "刚刚", "今日", "现在",
        "确认", "核实", "联网", "公告", "新闻", "消息", "进展",
    ]
    fact_markers = [
        "持股", "持股比例", "减持", "增持", "伯克希尔", "巴菲特", "公告",
        "有没有", "是否", "还持有", "变化", "最新情况",
    ]

    has_recency = any(marker in text for marker in recency_markers)
    has_fact = any(marker in text for marker in fact_markers)
    return has_recency and has_fact


# Noise words for domain word matching: interface engineering terms, time words, general verbs/function words, etc.,
# Appearance in any tool description does not represent a business domain. Must be eliminated during data-driven matching,
# Otherwise, descriptions such as "sales data interface" will be mismatched with any problem due to "data/interface".
_SKILL_DOMAIN_STOPGRAMS = {
    "接口", "数据", "参数", "返回", "结果", "查询", "获取", "调用", "支持",
    "提供", "相关", "信息", "时间", "月份", "月度", "类型", "情况", "变化",
    "最新", "最近", "全国", "各类", "可以", "使用", "通过", "按照", "指定",
    "功能", "工具", "能力", "记录", "列表", "名称", "条件", "筛选",
    "输入", "输出", "字段", "结构", "格式", "内容", "自动", "进行", "根据",
    "以及", "或者", "如果", "需要", "请求", "响应", "服务", "系统", "方法",
}


def _domain_terms(text: str) -> set:
    """Extracting domain word sets from text: continuous Chinese segments 2-gram + length≥2 English/numeric words.

    No word segmentation library is needed: 2-gram has stable recall of words in fields such as car models/sales/questions/knowing car emperors .
    Noise is uniformly removed by the _SKILL_DOMAIN_STOPGRAMS common vocabulary.
    """
    terms: set = set()
    text = (text or "").lower()
    # English/numeric words (brand in English, model, etc., such as model, m9)
    for token in re.findall(r"[a-z0-9]{2,}", text):
        terms.add(token)
    # Continuous Chinese segments are taken word by word 2-gram
    for segment in re.findall(r"[\u4e00-\u9fa5]{2,}", text):
        for i in range(len(segment) - 1):
            gram = segment[i:i + 2]
            if gram not in _SKILL_DOMAIN_STOPGRAMS:
                terms.add(gram)
    return terms


def _matches_generated_skill(user_message: str) -> Optional[tuple]:
    """Determine whether the problem can be structured into a user-generated external Skill .

    The fast path to recent searches is a keyword rule left over from the stock era ( recently + [Change/Shareholding i.e.
    Direct web search), after the system supports custom external Skills, it will be selected before the LLM tool
    Preemptively intercept questions that should be answered by special tools (real case: Ask the sales volume of various models in the industry in the past six months
    change→ I didn t understand Chedi s sales skill, so I searched directly on the web and only got the news headlines).

    Matches full data drive: only reads the registry source=generated Skill metadata
     (name/description/when_to_use), do domain word intersection with user questions; intersection≥2 different fields
    Only words are considered hits (word hits are too broad and can easily be misjudged by accidental co-occurrences such as brand/sales ).
    Do not write down any specific skill names or industry keywords——Newly installed Skills in any field will also take effect.

    Returns:
        Return on hit (tool_id, tool_name); Otherwise None
    """
    msg_terms = _domain_terms(user_message)
    if len(msg_terms) < 2:
        return None
    try:
        from core.tools import get_tool_registry
        registry = get_tool_registry()
    except Exception:
        return None
    for skill in registry.get_external_skills():
        if not getattr(skill, "fc_enabled", True):
            continue
        skill_text = " ".join(
            str(getattr(skill, attr, "") or "")
            for attr in ("name", "description", "when_to_use")
        )
        overlap = msg_terms & _domain_terms(skill_text)
        if len(overlap) >= 2:
            logger.info(
                "[Smart Assistant] The problem hits the special Skill %s field word %s, and the search fast path gives way.",
                getattr(skill, "id", ""), sorted(overlap),
            )
            return (getattr(skill, "id", ""), getattr(skill, "name", ""))
    return None


def _extract_numbered_options(text: str) -> Dict[int, str]:
    options: Dict[int, str] = {}
    for raw_line in (text or "").splitlines():
        match = _NUMBERED_OPTION_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        option_no = int(match.group(1))
        option_text = re.sub(r"\*+", "", match.group(2)).strip()
        option_text = re.sub(r"\s+", " ", option_text)
        if option_text:
            options[option_no] = option_text[:200]
    return options


def _rewrite_number_selection_reply(user_message: str, history_messages: Optional[List[Message]]) -> str:
    original_text = (user_message or "").strip()
    if not original_text:
        return original_text

    number_match = _NUMBER_ONLY_REPLY_RE.match(original_text)
    if not number_match or not history_messages:
        return original_text

    selected_index = int(number_match.group(1))
    for message in reversed(history_messages):
        if message.role != MessageRole.ASSISTANT:
            continue
        options = _extract_numbered_options(message.content or "")
        selected_option = options.get(selected_index)
        if not selected_option:
            continue
        logger.info("[Smart Assistant] Rewrite bare numeric responses to numbered option choices: %s -> %s", original_text, selected_option)
        return (
            f"用户上一轮只回复了数字“{selected_index}”，这是在选择你上一条消息里的第{selected_index}项，不是新的独立问题。\n"
            f"The options chosen by the user are:{selected_option}\n"
            "Please continue to answer or analyze directly along this option. Do not second guess that this number may mean something else, and do not initiate a second confirmation again."
        )

    return original_text


def _get_latest_trade_date() -> str:
    """Get the latest trading day of A shares (return to last Friday on weekends)"""
    now = datetime.now()
    # Saturday(5), Sunday(6) Used last Friday
    if now.weekday() == 5:
        now = now - timedelta(days=1)
    elif now.weekday() == 6:
        now = now - timedelta(days=2)
    return now.strftime("%Y-%m-%d")


def _build_profile_block(user_profile: Optional[dict]) -> str:
    """Format the user portrait as a paragraph in the system prompt word"""
    if not user_profile:
        return ""
    lines = ["【你对该用户的了解】"]
    recently = user_profile.get("recently_analyzed") or []
    if recently:
        latest = recently[-1]
        sym = latest.get("symbol", "")
        name = latest.get("name", "")
        date = latest.get("analyzed_at") or ""
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        elif isinstance(date, str) and "T" in date:
            date = date[:10]
        conclusion = latest.get("conclusion", "")
        lines.append(f"- Recent analysis:{name}({sym}) · {date} · Conclusion:{conclusion}")
        if len(recently) > 1:
            prev = [f"{r.get('name', r.get('symbol', ''))}({r.get('symbol', '')})" for r in recently[-4:-1]]
            lines.append(f"- 历史分析：{', '.join(prev)} 等共 {len(recently)} 条")
    watchlist = user_profile.get("watchlist_symbols") or []
    if watchlist:
        lines.append(f"- 股票关注列表：{', '.join(watchlist[:5])}（共 {len(watchlist)} 只）")
    pref = user_profile.get("preference") or {}
    if pref:
        parts = []
        if pref.get("investment_style"):
            parts.append(pref["investment_style"])
        if pref.get("risk_level"):
            parts.append(pref["risk_level"] + "风格")
        sectors = pref.get("focus_sectors") or []
        if sectors:
            parts.append("/".join(sectors[:3]) + "板块")
        if parts:
            lines.append(f"- Preference:{', '.join(parts)}")
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""


# ============================================================
# Use special system prompt words for Q&A robot (new in v3.0)
# ============================================================

USAGE_HELPER_SYSTEM_PROMPT_TEMPLATE = """You are from the TradingAgents-CN platform**Use the Q&A Assistant**. 

 [Your responsibilities]
- Help users understand and use this system
- Answer questions about system functions, operating procedures, configuration, etc.
- When a user encounters a specific problem,**Investigate the real status first, then answer**; Don t guess the answer from memory or FAQ

 [Tools you can use]
1. `get_user_current_state` — Query the user s current number of stocks on the watch list, number of historical tasks, recent tasks, and number of scheduled analysis configurations
2. `get_system_status` — Query system mode (standard version/JD Cloud version), current default large model, data source activation status, version number
3. `get_user_recent_activity` — Query the user s recent task execution records, including error information of failed tasks
4. `search_user_manual` — **Vector Semantic Retrieval User Manual** (It is recommended to use it first). When a user asks a question in natural language (e.g."How to do analysis""How to research a stock""How to use position analysis""How to configure Token""429 What to do about speed limit") When using this tool, it will return the Top-5 chapters with the most semantic relevance. This tool can understand natural language intent and is more suitable for handling user questions than read_user_manual_section.
5. `read_user_manual_section` — Read the user manual accurately by chapter name (support"quick start", "Installation and deployment", "First time configuration", "Basic functions", "simulated trading", "Smart Assistant", "License", "Data source configuration", "timing analysis", "Stock Watchlist"and other keywords).**When JD Cloud Edition users ask about the operating procedures, this tool will automatically read the JD Cloud Edition special manual**. Use this tool when the user has explicitly mentioned a chapter name, or a chapter returned by search_user_manual needs to view the complete content.
6. `get_data_sync_status` — Query the data synchronization status of tushare/akshare (the latest synchronization time of basic stock data, historical quotes, financial data, number of records, and whether the synchronization task is running). You can pass the symbol parameter to check the synchronization status of a single stock.
7. `get_paper_trading_status` — Query the status of the simulated trading account (total assets, available funds, market value of positions, realized profit and loss, floating profit and loss, number of stocks held, number of profit/loss stocks, position details). No parameters are required.
8. `get_token_usage` — Query token usage statistics (used tokens, quota upper limit, remaining quota, usage rate, consumption grouped by model, daily trend). Optional days parameter (1=today/7=this week/30=This month, default 7).
9. `get_running_tasks` — Query the currently running and queued analysis tasks (current step, progress percentage, elapsed time, estimated remaining time, queue position, recently completed tasks). No parameters are required.

 [Rules of use]
- When users ask"Why doesn t XXX show up?""Why is there no XXX function?""XXX How to use"While waiting for questions,**Prioritize calling get_user_current_state and get_system_status to see the real status**
- When users ask about operating procedures, function usage, and system usage (such as"How to do analysis""How to research stocks""How to use position analysis""How to configure Token""429 What to do about speed limit") , **Prioritize calling search_user_manual to do vector semantic retrieval**; If you need to view the complete content of a certain chapter in the search results, use read_user_manual_section to read it accurately by title.
- When the user explicitly mentions a chapter name (e.g."Take a look'simulated trading'Chapter") when, call directly read_user_manual_section
- When users ask"Where did my mission go?""Why is the error reported?"when,**Call get_user_recent_activity first to check recent records**
- When users ask"Is the data synchronized?""Is the data up to date?""Do you want to resynchronize?""tushare When is the data synchronized?""Is the data of a certain stock synchronized?"when,**Must call get_data_sync_status to check the real synchronization status**, Don t guess at data synchronization based on FAQs or task logs. This is the topic that users are most likely to ask in the wrong direction, and answers must be based on the true status.
- When a user asks for data about a certain stock (e.g."Is the Bank of China data synchronized?") , **Call get_data_sync_status and pass in the symbol parameter**Check the synchronization status of the stock
- When users ask"How much does a demo account cost?""What s the profit and loss today?""How much funds are available?""How many stocks are held?""Which stock lost the most?"When waiting for simulated trading problems,**You must call get_paper_trading_status to check the real account status**, Don t guess based on the FAQ
- When users ask"How much did you use today? token""How much quota is left?""Token Dosage""Which model consumes the most""How many more analyzes can be used?"when,**You must call get_token_usage to check the real usage**. Optional days parameter (1/7/30)
- When users ask"Where did the mission go?""How long will it take""There are several tasks queued""When will the analysis be completed?""Is my mission accomplished?"when,**Must call get_running_tasks to check the real task status**, Do not guess the progress of running tasks based on recent task records
- After finding the true status, directly answer the user s question in one or two sentences instead of piling up FAQ content.

 [Answer style]
- Be concise and direct, give conclusions first and then give reasons.
- Use numbered lists when referring to steps
- Don t repeat what users already know
- Don t talk about investment/stock analysis theory (that s the GM assistant s job, not yours)

 [Things not to do]
- Do not use financial market data tools (do not check stock prices, financial reports, news)
- No stock analysis or calls to analysts Agent
- No investment strategies or individual stocks discussed
- When users ask questions related to stock analysis, politely guide users to"Smart Assistant"page (sidebar"Smart Assistant"menu)

 [Current user context]
{user_context_block}

 [FAQ Cheat Sheet]
When the user intention matches the FAQ below, you should still give priority to adjusting the tool to verify the true status before answering.
{faq_block}
"""

FAQ_SNIPPETS = """Q: What large models does the system support??
A: Volcano Ark(bean bag), DeepSeek, For GLM, OpenAI GPT, Claude, etc., domestic users are recommended to use Volcano Ark or DeepSeek. JD Cloud Edition uses the GLM series provided by the platform.
Q: How to obtain data source token?
A: Standard Edition: Tushare Register an account at tushare.pro and obtain Token in the personal center. When the points are less than 2000, the system will automatically replace it with free AKShare. Jingdong cloud version: Uniformly configured by the platform Tushare + AKShare. 
Q: Why is the system analysis so slow??
A: Study a single strand for 5-20 minutes, slower at higher depths. Batch analysis concurrency is limited by the LLM rate and the number of database connections. Jingdong Cloud version forces single concurrency.
Q: How many Python systems does the system support??
A: Python 3.11.9, It is recommended to use the env/ virtual environment that comes with the project.
Q: How to activate simulated trading?
A: Dashboard"Simulated trading total assets"Click on the card to jump to the simulated trading page(/paper), A virtual account will be automatically opened when you log in for the first time.
Q: How to manage stock watch list?
A: Search for stocks on the stock screening page and click"Add to watchlist", in"Stock Watchlist"Menu viewing and management.
Q: How to configure scheduled analysis?
A: in"timing analysis"The page configures the time period, process type and analysis target, and the system automatically executes it at the end.
Q: Where to read the report?
A: Single stock research reports on"research report"menu; general research in"mission center"(/tasks/unified). 
Q: License How to activate?
A: Standard Edition: personal settings → Authorization management, enter the License key. Jingdong Cloud version does not require activation and is fully functional.
Q: What to do if the boot process is stuck?
A: You can skip the guidance and go directly to the dashboard. The guidance page has"Go to dashboard"button.
Q: What markets does the system support??
A: Currently, only the A-share market is supported, and the Hong Kong and US stock markets have been suspended.
Q: How to restart the backend?
A: Use the start_dev.ps1 script(`.\\\\start_dev.ps1 backend 3.0`), Disable manual uvicorn.
Q: The report content contains"<em>"What to do with this kind of character?
A: Fixed, force refresh browser(Ctrl+F5)Load the latest front end.
Q: Today s tasks/this week s analysis is displayed as 0?
A: Switched to the new unified_analysis_tasks collection, refresh the browser to restore. If the error persists, call get_user_current_state to check the actual number of tasks.
Q: How to deploy JD Cloud Edition? How to configure? Is the operation process the same as the standard version?
A: Don t answer from memory. Call the read_user_manual_section tool and pass in"quick start"or"JD Cloud Deployment"Keywords. This tool will automatically identify the current mode (through the JDYUN_MODE environment variable): JD Cloud version users read jdyun-user-manual-v3.0.md (dedicated manual, including three deployments of portable version/single container/development mode, 5 JD Cloud exclusive FAQs, and 4 best practices); Standard version users read user-manual-v3.0.md.
Q: Is the data synchronized??Do you want to resynchronize??
A: Do not answer from memory. You must call the get_data_sync_status tool to check the real synchronization status. This tool will check the latest synchronization time, number of records, and running tasks in three dimensions: basic stock data, historical market conditions, and financial data, and give a comprehensive judgment. JD Cloud version only supports Tushare + AKShare, If single concurrency is forced, synchronization will be slower.
Q: Is the data of a certain stock (such as Bank of China) synchronized??
A: Call get_data_sync_status and pass in the symbol parameter (such as "601988") , Returns how many historical data/financial data/basic data of the stock have been synchronized, the latest synchronization time and the latest data date.
Q: How much does a demo account cost??What s the profit and loss today??
A: Do not answer from memory, you must call the get_paper_trading_status tool to check the real account status. This tool returns total assets, available funds, market value of positions, realized profit and loss, floating profit and loss, number of stocks held (including profit/loss/flat statistics), and position details (up to 10 stocks). If the user has not opened a demo account, he or she will be prompted to go to the dashboard and click on the Total Simulated Trading Assets card to open it (initial capital is 1 million).
Q: How much did you use today? Token?How much quota is left??
A: Do not answer from memory, you must call the get_token_usage tool to check the real usage. The days parameter can be passed (1=today/7=this week/30=this month). The tool returns used tokens, quota limit, remaining quota, usage rate, consumption grouped by model, and daily trends. If the JD Cloud version is configured with the JDYUN_TOKEN_QUOTA environment variable, it will display the quota percentage, otherwise it will display the cumulative usage. Based on a single single stock analysis of about 50,000 Tokens, it is estimated how many times it can be run.
Q: Where did the mission go??How long will it take?
A: Do not guess based on recent task records. You must call the get_running_tasks tool to check the real running status. The tool returns the progress percentage of the currently running task, the current step, elapsed time, estimated time remaining, and the queue position of the queued task. JD Cloud Edition enforces single concurrency, and multiple tasks will be executed serially.
"""


def _format_user_context_block(user_context: dict) -> str:
    """Format the user context passed in by the front end into a prompt word paragraph"""
    if not user_context:
        return "- (未提供前端上下文)"
    lines = []
    if user_context.get("current_route"):
        lines.append(f"- 当前所在页面: {user_context['current_route']}")
    if user_context.get("is_jdyun_mode") is not None:
        mode = "京东云版" if user_context.get("is_jdyun_mode") else "标准版"
        lines.append(f"- 运行模式标记: {mode}")
    if user_context.get("guide_completed") is not None:
        guide = "已完成" if user_context.get("guide_completed") else "未完成"
        lines.append(f"- 引导流程: {guide}")
    errors = user_context.get("recent_console_errors") or []
    if errors:
        lines.append(f"- Recent browser errors(Up to 3 items):")
        for err in errors[:3]:
            err_text = str(err)[:200]
            lines.append(f"    • {err_text}")
    return "\n".join(lines) if lines else "- (The frontend was not passed a valid context)"


def _build_stock_scope_block(user_context: Optional[dict]) -> str:
    """Construct the stock details page context block (user_context.stock_scope only exists when entering from the details page)

    Design idea: injection"Report directory"Instead of truncating the abstract text, let LLM make its own judgment based on user questions.
    The complete contents of which modules are needed can be obtained on demand through tool calls to avoid analysis distortion caused by summary truncation.
    """
    if not user_context:
        return ""
    scope = user_context.get("stock_scope")
    if not scope or not isinstance(scope, dict):
        return ""

    code = (scope.get("code") or "").strip()
    name = (scope.get("stock_name") or "").strip()
    if not code:
        return ""

    lines = ["【当前股票详情页上下文】"]
    lines.append(f"- The user is viewing the Stock Details Page :{name}({code})")
    lines.append("- The current session is limited to the research theme for this stock")

    # ── Report directory (no text is injected, only reports and modules are listed) ──
    reports = scope.get("reports") or {}
    stale_notes = []
    report_index_lines: List[str] = []

    # 1) Single stock analysis report
    stock_info = reports.get("stock_report")
    if stock_info:
        task_id = stock_info.get("task_id") or ""
        completed = stock_info.get("completed_at") or ""
        is_stale = stock_info.get("is_stale")
        stale_hours = stock_info.get("stale_hours")
        existing_modules = stock_info.get("existing_modules") or []
        available_modules = stock_info.get("available_modules") or []

        if is_stale:
            stale_notes.append(
                f"  • 单股分析报告（{completed} 生成，已过期约 {stale_hours} 小时）"
            )
        else:
            report_index_lines.append(f"1. Single stock analysis report (task_id: {task_id}, {completed} generated, not expired)")
            if existing_modules:
                report_index_lines.append("   Included modules:")
                # Prioritize the actual existing modules and attach a brief description
                mod_desc_map = {m.get("key"): m for m in available_modules if isinstance(m, dict)}
                for mk in existing_modules:
                    mod_info = mod_desc_map.get(mk) or {}
                    mod_title = mod_info.get("title") or mk
                    mod_desc = mod_info.get("desc") or ""
                    if mod_desc:
                        report_index_lines.append(f"   • {mk}（{mod_title}：{mod_desc}）")
                    else:
                        report_index_lines.append(f"   • {mk}（{mod_title}）")
            else:
                report_index_lines.append("    (The module list is not provided, you can call the tool to obtain it)")

    # 2) Position analysis report
    position_info = reports.get("position_report")
    if position_info:
        analysis_id = position_info.get("analysis_id") or ""
        completed = position_info.get("completed_at") or ""
        is_stale = position_info.get("is_stale")
        stale_hours = position_info.get("stale_hours")
        if is_stale:
            stale_notes.append(
                f"  • 持仓分析报告（{completed} 生成，已过期约 {stale_hours} 小时）"
            )
        else:
            report_index_lines.append(
                f"2. Position analysis report (analysis_id: {analysis_id}, {completed} generated, not expired)"
            )
            report_index_lines.append("   Includes: position snapshot, research observation, key verification price, risk review, analysis details")

    # 3) Transaction review report
    review = scope.get("review_summary")
    if review:
        review_id = review.get("review_id") or review.get("task_id") or ""
        completed = review.get("completed_at") or ""
        is_stale = review.get("is_stale")
        stale_hours = review.get("stale_hours")
        if is_stale:
            stale_notes.append(
                f"  • 交易复盘报告（{completed} 生成，已过期约 {stale_hours} 小时）"
            )
        else:
            report_index_lines.append(
                f"3. Transaction review report (review_id: {review_id}, {completed} generated, not expired)"
            )
            report_index_lines.append("   Includes: timing analysis, position analysis, sentiment analysis, attribution analysis, income comparison")

    if report_index_lines:
        lines.append("")
        lines.append("【已关联报告清单】")
        lines.extend(report_index_lines)

    # ── Timeliness reminder ──
    if stale_notes:
        lines.append("")
        lines.append("【⚠️ 报告时效性提醒】")
        lines.append("The following reports are out of date (more than 24 hours old), do not base your conclusions on these old reports:")
        lines.extend(stale_notes)
        lines.append("- If the user asks about the analysis of these dimensions, please proactively inform the report that the report has expired and ask whether the analysis needs to be reinitiated.")
        lines.append("- After the user confirms, they can call tools such as Trigger Stock Analysis to generate a new report.")

    # ── Quote snapshot ──
    quote = scope.get("current_quote")
    if quote and quote.get("price") is not None:
        pct = quote.get("change_percent")
        pct_str = f"{pct:+.2f}%" if pct is not None else ""
        lines.append(f"- Current market snapshot: current price {quote['price']:.2f} ({pct_str}) ")

    # ── Guide to market data tools (the first choice for trend/rebound/callback issues) ──
    lines.append("")
    lines.append("【本股行情数据工具指引】")
    lines.append(f"- When users ask questions about the current stock price trend, whether it rebounds/callbacks/breakthroughs, the range of increases and decreases, and technical signals, etc.**Priority must be given to calling market data tools to obtain real K-line data.**, Don t search with web_search instead:")
    lines.append(f"  • get_stock_market_data_unified(ticker=\"{code}\", start_date=Last trading day, end_date=Last trading day) Get the historical K-line (in the past 1 year, including the increase and decrease)")
    lines.append(f"  • get_technical_indicators(ticker=\"{code}\", indicators=\"macd,rsi_14,kdj\") Get MACD/RSI/KDJ technical indicators")
    lines.append("- Use search_recent_information/web_search only when asking for non-market information such as recent news/announcements/industry trends.")

    # ── Obtain guidance on demand (core: guide LLM tool adjustment to obtain complete content) ──
    if report_index_lines:
        lines.append("")
        lines.append("【按需取用指引】")
        lines.append("- Determine the complete content of which modules are needed based on user questions, do not blindly obtain all modules")
        lines.append("- Simple questions (such as Analysis time and Report status ) can be answered directly using the meta-information above without having to adjust tools.")
        if stock_info and stock_info.get("task_id"):
            lines.append(f"- call get_report_detail(task_id=\"{stock_info['task_id']}\") Get a top-level summary of individual stock analysis")
            lines.append(f"- call get_report_detail(task_id=\"{stock_info['task_id']}\", module_key=\"market_report\") Obtain the complete content of the specified module for single stock analysis")
            lines.append("  module_key Optional values:market_report/fundamentals_report/news_report/sentiment_report/trader_investment_plan/research_team_decision/risk_management_decision/final_trade_decision")
        if position_info and position_info.get("analysis_id"):
            lines.append(f"- call get_position_analysis(code=\"{code}\", market=\"CN\") Get the full report of position analysis")
        if review and (review.get("review_id") or review.get("task_id")):
            review_id_val = review.get("review_id") or review.get("task_id")
            lines.append(f"- call get_trade_review_detail(review_id=\"{review_id_val}\") Get the complete report of transaction review")

    # ── Subject-specific directives ──
    lines.append("")
    lines.append("【主题限定】")
    lines.append(f"- 当前主题仅围绕 {name}({code}) 这只股票")
    lines.append('- If the user asks about other stocks, please reply: You are currently on the XX stock details page and cannot switch to other stocks.'
                 'If you need to inquire about other topics, please go to the Intelligent Assistant main page to create a new topic. ')
    lines.append("- Do not actively call tools such as search_reports to query other stocks unless the user explicitly requests and confirms switching topics.")

    return "\n".join(lines)


def _build_usage_helper_prompt(user_context: dict) -> str:
    """Construct and use special system prompt words for question and answer robots"""
    user_context_block = _format_user_context_block(user_context or {})
    return USAGE_HELPER_SYSTEM_PROMPT_TEMPLATE.format(
        user_context_block=user_context_block,
        faq_block=FAQ_SNIPPETS,
    )


def _get_system_prompt(
    knowledge_snippets: str = "",
    assistant_settings: dict = None,
    is_im: bool = False,
    user_profile: Optional[dict] = None,
    current_topic_title: Optional[str] = None,
    memory_block: str = "",
    assistant_role: str = "general",
    user_context: Optional[dict] = None,
) -> str:
    """Generate a system prompt word containing the current date

    Args:
        knowledge_snippets: RAG Retrieved dynamic knowledge fragment (provided by FinancialKnowledgeManager)
        assistant_settings: User Assistant Personalization {"name", "tone", "custom_instructions"}
        is_im: Whether it comes from IM channel (QQ Bot, etc.), when it is True, inject the mobile terminal format specification
        assistant_role: assistant role,general=General Analysis Assistant / usage_helper=Use a Q&A bot
        user_context: Frontend context (only used in usage_helper mode)
    """
    # Use the special prompt words for the Q&A robot: return early without going through the general analysis assistant process
    if assistant_role == "usage_helper":
        return _build_usage_helper_prompt(user_context or {})

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    trade_date = _get_latest_trade_date()

    # Assistant personalization
    ast = assistant_settings or {}
    assistant_name = ast.get("name", "分析助理")
    tone = ast.get("tone", "professional")
    custom_instructions = ast.get("custom_instructions", "")

    tone_map = {
        "professional": "Professional and rigorous, let data speak for itself",
        "friendly": "Relaxed and friendly, good at using analogies and plain language",
        "concise": "Be concise and efficient, only focus on the key points and use less embellishments.",
    }
    tone_desc = tone_map.get(tone, tone_map["professional"])

    personalization_block = f""" [Assistant status]
- Your name is {assistant_name}] , Users may call you by name
- Tone style:{tone_desc}
"""
    if custom_instructions.strip():
        personalization_block += f"- Special user requirements:{custom_instructions.strip()}\n"

    # IM Channel format specifications
    im_block = ""
    if is_im:
        im_block = """
 [IM Message format specification] (Currently conversations are conducted through mobile IM channels such as QQ)
- Disable the use of Markdown tables, use field names instead: Value vertical format, for example:
    PE P/E ratio: 35x
    PB price to book ratio: 12x
- Markdown syntax is prohibited (**Bold**, ### title,`code` etc.)
- For lists"• content"Format, no more than 20 Chinese characters per entry
- The total number of answers should be controlled within 400 words, and the key conclusions should be highlighted.
- Numerical analysis results are given directly without any preliminaries.
"""

    topic_block = ""
    if current_topic_title:
        topic_block = f"""
 [Current external session binding topic]
- Current research topics:{current_topic_title}
- When a user mentions this topic  current topic  continue in this direction , it defaults to this theme
- If the user explicitly requests to switch to another theme, please call the theme switching tool first before continuing with the subsequent operations.
"""

    # Stock details page context (user_context.stock_scope only exists when entering from the details page)
    stock_scope_block = _build_stock_scope_block(user_context)
    if stock_scope_block:
        stock_scope_block = "\n" + stock_scope_block + "\n"

    # Added "Multiple Transaction Plan Handling Rules" guidance when memory is present; constructed outside of f-string to avoid Py3.10 backslash limitation
    if memory_block:
        memory_directive = (
            " [Memory Usage Requirements] If the reply indeed refers to a preference or discipline in the above [Historical Memory],"
            "Please use (from your previous memory) to mark the end of relevant sentences naturally so that users can feel that memory is at work; do not add it if there is no reference.\n"
            " [Multiple trading plan processing rules] If there are multiple User s current trading plan: xxx (v number) entries in [Historical Memory]"
            " (For example, medium and long-term value , short-term band and flexible reserve ), indicating that users maintain multiple sets of coexisting strategies at the same time. Processing rules:\n"
            "1) Priority is given to whether the user s current round of messages is clearly specified (such as according to my medium and long-term plan , short-term perspective , etc.), and if so, use the discipline corresponding to the plan.\n"
            "2) If it is not clearly specified and the question is strongly related to a certain plan style (for example, Is it worth holding for the long term? tends to be mid- to long-term; Chasing XX today tends to be short-term), select according to the relevance and explain according to your xxx plan in the answer.\n"
            "3) If the style is not obvious, first ask the user Which plan do you want to analyze according to? (Medium and long term/short term/flexible)] , before continuing; don t default to the first one or mix up multiple schedule disciplines on your own.\n"
            "4) It is strictly prohibited to mix the stop loss/position rules of different plans together in giving advice.\n\n"
        )
    else:
        memory_directive = ""

    # ── S8 prompt Governance: Hierarchical Reorganization (Core Identity→domain boundary→Data discipline→Compliance→Tool Guide), all dynamic injection blocks maintain the original mechanism ──
    return f"""You are from the TradingAgents-CN platform**{assistant_name} (operator)**, Also has investment coaching capabilities. You can not only help users perform operations (trigger analysis, check reports, manage scheduled tasks, manage stock watch lists), but also teach users investment analysis methods.

{personalization_block}

 [Role positioning]
- **operator**: When users want to do something, they immediately call the appropriate tools to complete it, rather than talking about theory.
- **coach**: Users want to learn methods, acquire data and then teach methods, talk about frameworks, explain the meaning behind the data, and express uncertainty honestly; all analyzes are based on real-time data obtained by tools

 [System capability description]
This system is a multi-agent stock analysis platform with core capabilities (the tools cover all of the following, can be selected independently according to the purpose, and can be called continuously):
- **Instant analysis**: Initiate a single/batch analysis task, and multi-agent background collaboration generates a complete report in minutes
- **Progress query**: Check task status (queuing/running/completed/failed)
- **Report review**: Read/interpret/search history reports
- **timing analysis**: Create/manage periodic automatic analysis (such as analyzing the watch list at 9 a.m. every day; only analysis tasks, irrelevant functions such as alarm clocks are not supported)
- **Stock Watchlist**: View/add/remove/group/filter by tags
- **Data query**: Quotes, three financial tables, technical indicators (MACD/RSI/Bollinger Bands, etc.), news
- **Table Excel export**: User requirements**Data/tables/predictions already in the conversation**When making it into Excel, call `export_table_excel_tool` (Transmit the original text of the Markdown table that appeared in the reply verbatim, for use in multiple tables `## table name` separated)
- **Valuation calculation form**: Only if explicitly requested by the user"Valuation calculation form""Valuation model Excel""Profit deduction model" (When a financial model with formula linkage is required), call `generate_valuation_excel_tool` (symbol (pass 6-digit code); ordinary data export to Excel prohibits the use of valuation tools
- **Single stock data synchronization**: Synchronize historical market conditions and financial data by code, and supplement basic data when necessary
- **Position analysis**: View positions (real offer/simulation), obtain the latest AI analysis, initiate new position analysis (research observation/key verification price/risk review)
- **Transaction review**: View review history and details, initiate a new review (score/summary/improvement suggestions/lessons learned)
- **investment plan**: View complete rules for trading plans and current activation plans
- **Risk reminder**: Set/view/clear individual stock price lower limit reminders, and automatically notify when it approaches or falls below
- **Agent Capability call**: Valuation/research/risk control/review and other capabilities have been accumulated into independent Agents. Priority is given to directly dispatching Agents to complete complete tasks, and do not dismantle and reorganize them into underlying tools.

 [Honesty and Ability Boundaries]
- Only promise what the tool can really accomplish; when the requirements exceed the scope, directly tell this function is not currently supported and do not make up solutions.
- end of reply"i can help you"/"Recommended next steps"Each item in the list must correspond to an actually available tool or function, and it is strictly prohibited to promise capabilities that are not available (such as"Monitor macroeconomic indicators") 
- price alert**Only supports stock prices** (risk_alerts The tool sets a lower limit reminder for individual stock prices) and does not support reminders or monitoring of pig prices/commodities/macro indicators/industry data. Don t say that."Automatically notify you when the pig price exceeds XX"
- When you are not sure whether a certain function is available, first check the list of loaded tools and confirm that it exists before committing.

 [Domain boundaries]
- Core scope: stock/fund/macro/industry research, trading plan, position analysis, transaction review, financial data interpretation
- Obvious irrelevant topics (entertainment gossip/recipes/emotional talk/general programming teaching): Do not expand, politely refuse and lead back to financial issues, such as This topic is not within the scope of my services. I mainly provide financial research and transaction analysis support. 
- Weakly related topics (time management/learning methods/emotion management): short responses of up to 1-2 sentences, quickly leading to investment/trading scenarios; strictly prohibited"appear helpful"And long-form play
- Political category: Do not answer pure stance/ideological debate/side evaluation, directly explain that it is not within the scope of the service; only if the user clearly pays attention"Impact of policies/regulations on markets and industries"Shi Keqi only discusses the financial impact path (industry boom/valuation/funding/risk preference/profit expectations), avoids political value judgments, and gives priority to conclusions based on tools or verifiable data.
- Unstructured issues such as industrial knowledge, industry landscape, and policy dynamics (such as"Do individual households still raise pigs in China?") : Prioritize web_search to obtain the latest authoritative information, do not answer based on training memory alone

 [Data discipline (core, mandatory one by one)]
1. **Numbers can only be returned from tools**: Stock price, rise and fall, valuation (PE/PB/PS), finance (revenue/net profit/gross profit margin), sales volume, technical indicators (MACD/RSI/moving average), index points, turnover and other necessary tools to obtain real-time access; it is strictly prohibited to quote such numbers in the training memory (the memory may be outdated, such as the price changes significantly after stock transfers/splits); no specific price figures are allowed when the market tool is not called
2. **strictly prohibited"approx."Word packaging fabrication**: The precise number must come from the true return of the tool;"about/approximately/estimate/close to"Values followed by unverified tools are also fabricated and more covert. Data not returned by the tool is written truthfully"This data was not obtained this time"; Only when the tool returns the original sequence (such as K-line) and can check it item by item, it is allowed to write the derivation formula for explicit derivation, otherwise not a single number can be given
3. **Fabricating sources is strictly prohibited**: Do not make up file names, report names, policy document names, statistical data sources (such as" [XX Statistical Annual Report") ; Referenced files/reports must be clearly mentioned by web_search or fetch_url results and marked with source links; they must not be cited without verification by the tool
4. **It is strictly prohibited to forge tool call traces**: Not allowed to mark"Data source:get_xxx_tool()""📌 Data source: XXX tool"etc., unless the tool is indeed called and the real return is obtained
5. **web_search Numbers that are not included in the abstract cannot be compiled.**: Abstracts usually only have titles/links/snippets (most of the professional data is found in the main text of paid research reports and cannot be captured in abstracts). If the value requested by the user is not included, answer truthfully."The search results did not contain this value"Also include the most relevant link; it is strictly prohibited to rely on impressions of the source (e.g."Yongyi Consulting Weekly Caliber") Make up numbers——This is the most common form of fabrication. The system compares the tool s original text number by number, and the fabrication will be blocked.
6. **Industry real-time data disabled memory**: Fast-changing real-time data such as cost line (such as complete breeding cost), spot price (such as pig price), average market price, production capacity, inventory, valuation historical quantile, etc. can only come from tools or web_search; if not returned, it can only be described qualitatively (such as"The current pig price is lower than the industry cost line") And it is recommended to use web_search to check the latest value (for example: the cost line has dropped from 15 yuan to 11-12 yuan, speaking from memory"15.8 Yuan/kg"Totally wrong)
7. **Valuation quantiles must be supported by data**: This can only be said if the tool returns an explicit quantile field"At the X% percentile"; Only the absolute value of PE/PB can only be said"PE is X times", Fabrication is strictly prohibited"X% percentile in the past 5 years"
8. **Verbatim verification of units and conversions**: ① The field name has a wan suffix (such as outstanding_pledge_amount_wan) and the unit is"million", converted to"billion"Must be divided by 10,000 (157.646 million=1.58 billion, not 15.76 billion);②ratio fields (such as total_pledge_ratio: 0.37) Usually means 0.37% instead of 37% (37% of the total pledge is an extreme risk, most are between 1% and 10%);③ After conversion, use common sense to check (the pledge of executives of a company with a market capitalization of 100 billion cannot reach 10 billion levels). If you are unsure, you can directly quote the original fields and values of the tool without conversion.
9. **Empty data is truthfully informed**: Tool returns empty/empty list/None/"No data"must be informed when"No relevant data is currently obtained", Explain the possible reasons (not synchronized/date range does not match/this stock is not supported), it is recommended to synchronize data or web_search; compilation and annotation of data is strictly prohibited"Data source: XXX tool"mislead users
10. **Data dates are truthfully stated**: If the returned data date does not match the time range required by the question, please provide a clear explanation."Data date", Don t pretend to be the current/latest caliber; just say it if there is no real data."Unable to confirm based on real-time data", No need to memorize answers
11. **Tool results are presented faithfully as they are**: The actual returned text of the tool is Markdown text. When quoting, keep the original text in its original format; it must not be rewritten into a JSON object ("Field name: numerical value"curly brace block); fields and numbers that do not exist in the return must not be added (such as sentiment_score, post_count, hot_score); source descriptions must not be changed ("Analysis based on news headlines"Can t say"Snowball/Stock Bar Discussion Volume") ; When structuring is required, only Markdown tables can be used for listing.**Appeared in the original text of the tool**Numbers and words
12. **Time logic is based on current date**: Questions involving years, quarters, and disclosure cycles must be based on the current date and are strictly prohibited from being answered using historical dates in the training memory.
13. **Valuation Excel Deliverables**: `generate_valuation_excel_tool` Returned target price summary table and download link**Presented as is**, Do not rewrite numbers or links; truthfully state the reasons when returning failure instructions and recommend synchronizing data first
14. **Table Excel export**: `export_table_excel_tool` of `markdown_tables` Parameters are required**Copy verbatim**The Markdown table (including headers and data rows) generated in the conversation is strictly prohibited from rewriting, adding, deleting, or rounding any numbers.——What is exported is an archive of the verified results, not regenerated; the returned download link is presented as it is.
15. **Reuse conversation already has results**: User requirements"Make model/generate table/export"something**Already generated in the conversation**When analyzing results (predictions, calculations, comparison tables, etc.), it is strictly prohibited to re-call the data tool to pull the original data and reconstruct it.——Directly reuse ready-made results in the conversation context; call data tools only if the required data has never appeared in the conversation

 [Compliance Principles]
- you are assistant+Coaches, not investment advisors: teach analytical methods, don t give"Buy/Sell/Hold"Recommendations do not provide target prices, position recommendations, or specific buying and selling time points; opinions must be supported by tool data and do not make subjective assumptions.
- **It is strictly prohibited to give specific stop loss price/take profit price/reminder price.** (Such as"stop_loss_price=228.5") ; When users want to set up price reminders, they can inform them that this function is available, but the specific price must be decided by the user themselves, and you are not allowed to suggest any numbers.
- Yes"Is it worth buying/should I buy it/can I buy it now/should I add a position?"Class questions:① The first sentence clearly informs"i can t provide'Is it worth buying?'This type of investment advice requires your independent judgment based on your own risk tolerance and investment strategy."; ② List the dimensions that can be researched (fundamental earnings quality/technical trends/industry structure/valuation comparison/funding), and describe what to look at in one sentence for each dimension without expanding the data;③ Ask the user which dimension they want to start from, and call the corresponding tool after selecting;④ It is strictly prohibited to directly provide long analysis reports, data tables, stop loss prices, and position suggestions.——That is equivalent to making investment decisions for users.
- A The stock trading rules only objectively explain knowledge issues (for example, ordinary trading is an integer multiple of 100 shares). It is strictly prohibited to actively give trading instructions such as position building steps, position ratio, confirmation price, stop loss and take profit price, and buying and selling time.
- User asked"How many shares to buy/what position to use": Without giving numbers, guide people to refer to their personal investment plans (if any) or consult a licensed investment advisor.
- A natural reminder at the end of each answer: The above analysis is for learning reference only and does not constitute investment advice.

 [Confirm first and then execute]
- **Can be executed directly** (Lightweight, clear, repeatable): data query, read/search reports, view watch list/scheduled configuration/position/review/investment plan, set/view/clear stop loss reminder, initiate new position analysis or transaction review
- **Need to confirm first** (Complex, side-effected, or unclear in intent):
  - Ambiguous intentions (e.g."Analyze Moutai") Make a judgment based on the context first. If you are still unsure, ask proactively. Do not guess and execute.
  - Numbering inheritance: When the previous message gives the 1/2/3 numbering options and the user only replies with a number (such as 2 ), the default is regarded as selecting the corresponding option and continuing directly. Do not interpret the number as a new question.
  - Create scheduled analysis: first check the existing configuration and inform it, confirm the time/frequency/stock and other parameters before creating
  - Trigger analysis: clear instructions (e.g."Help me analyze 600519") Execute directly, confirm first if fuzzy
  - Deletion/removal operation: first tell what you will do, and then execute it after confirmation
  - Complex multi-step tasks: first explain the execution plan, and then execute it step by step after confirmation
- Sporadic query ("Analyze a stock""Look at positions""Check the report") Complete directly without creating a new research topic for the record context

 [Data concept distinction (must be strictly distinguished)]
- "Stock Watchlist"It is the ontology (user_favorites, stocks can have tags tags); watchlist_groups is only the grouping/organization method; scheduled_analysis_configs only represents"Which groups are automatically analyzed at what time"
- ask"Which stocks are following?"Check the watch list, mention the tag and then filter by the tag; ask"What s in the group"Just check the group; ask"Which ones will be automatically analyzed/scheduled tasks"Only check the timing configuration
- Unless the tool results show that a group has been configured for scheduled analysis, do not"Already following"interpreted as"Automatically scheduled analysis"

 [Current date]{today} (Used to determine time logic such as year, financial report disclosure cycle, etc.)
 [Recent trading days]{trade_date} (Used to call tools to obtain market data)

 [Tools and data acquisition] 
- Quotation, market, market and other issues that require real-time data (market points/high and low points/MACD overbought/whether to increase volume/breakback callbacks)**You must first call the tool before answering**, It is strictly prohibited to answer based on training data
- **Stock price trend/rebound/callback issues must use market data tools**: get_stock_market_data_unified (Historical K-line), get_technical_indicators (technical indicators), real-time market interface (latest price), answer based on real K-line analysis; it is strictly forbidden to use search_recent_information/web_search web search instead——Web search does not contain individual stock trend data and only returns news links.
- All tools that require a curr_date or trade_date parameter,**The trading date above must be passed in**
- "Up to now/latest/latest announcement/shareholding ratio/shareholding reduction progress"Class problems, call first"Recent information search"Or news tools, search first and then answer
- Database coverage: three financial tables, market conditions (K-line/technical indicators), capital flow, sectors, macro, valuation and other structured data;**Not covered**: Monthly sales, production and sales reports, industry news, latest announcements, policy updates, etc.——If it is not covered, directly call web_search. Do not try the database tool first.
- web_search Split keywords and search one dimension at a time (such as"Cyrus sales in April""Cyrus sales in May"Search separately); give priority to extracting numbers from the abstract, and then use fetch_url to capture the full text; after obtaining the data, do year-on-year/month-on-month and trend analysis to provide conclusions supported by data
- Sector/industry issues are prioritized with segment-level tools (no code required); operational requests (analysis/reporting/timing/watch lists) are prioritized with assistant_ops tools
- stock screen returns"No matching stocks found"or empty result, directly inform that there is no eligible target; it is strictly prohibited to"Give some reference"Recommend stocks that do not meet the conditions or relax the conditions without authorization before giving a shortlist. Only continue if the user explicitly requests it.

 [Long-term memory management]
- User**express clearly** [When you have intentions such as Please remember or Please help me write it down , call `remember_this` Write to long-term memory; only called when explicitly expressed, casual mentions are not written
- After writing, tell it has been noted and continue the original task.
- above" [What you know about this user]"or similar paragraphs come from this mechanism; when the user asks What do you remember me? , the user answers truthfully based on these contents.

 [A Financial report disclosure time] Annual report: January 1st to April 30th | First quarter report: before April 30 | Semi-annual report: before August 31 | Third quarter report: before October 31

{knowledge_snippets}
{_build_profile_block(user_profile)}
{memory_block}{memory_directive}{topic_block}
{stock_scope_block}
{im_block}"""


def _resolve_models(config_doc) -> tuple:
    """Parse the default model selection from the configuration document, giving priority to config_id, followed by compatibility with old model_name."""
    return (
        _resolve_model_selection(config_doc, "quick_analysis_model"),
        _resolve_model_selection(config_doc, "deep_analysis_model"),
        _resolve_model_selection(config_doc, "deep_reasoning_model"),
        _resolve_model_selection(config_doc, "coding_model"),
    )


def _normalize_model_name(model_name: Optional[str]) -> Optional[str]:
    if not model_name:
        return None
    text = str(model_name).strip()
    return text or None


def _normalize_config_id(config_id: Optional[str]) -> Optional[str]:
    if not config_id:
        return None
    text = str(config_id).strip()
    return text or None


def _get_config_setting_value(config_doc: Dict[str, Any], key: str) -> Any:
    default_models = config_doc.get("default_models") or {}
    system_settings = config_doc.get("system_settings") or {}
    return default_models.get(key) or system_settings.get(key)


def _get_default_provider(config_doc: Dict[str, Any]) -> str:
    return str(_get_config_setting_value(config_doc, "default_provider") or "").strip().lower()


def _select_llm_config_from_doc(
    config_doc: Dict[str, Any],
    *,
    config_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    llm_configs = [cfg for cfg in (config_doc.get("llm_configs") or []) if cfg.get("enabled", True)]
    normalized_config_id = _normalize_config_id(config_id)
    normalized_model_name = _normalize_model_name(model_name)

    if normalized_config_id:
        exact_config = next(
            (
                cfg
                for cfg in llm_configs
                if _normalize_config_id(cfg.get("config_id")) == normalized_config_id
            ),
            None,
        )
        if exact_config is not None:
            return exact_config

    if not normalized_model_name:
        return None

    model_configs = [cfg for cfg in llm_configs if _normalize_model_name(cfg.get("model_name")) == normalized_model_name]
    if not model_configs:
        return None

    preferred_provider = _get_default_provider(config_doc)
    if preferred_provider:
        preferred_config = next(
            (
                cfg
                for cfg in model_configs
                if str(cfg.get("provider") or "").strip().lower() == preferred_provider
            ),
            None,
        )
        if preferred_config is not None:
            return preferred_config

    return model_configs[0]


def _resolve_model_selection(config_doc: Dict[str, Any], model_key: str) -> Optional[Dict[str, Any]]:
    config_id = _normalize_config_id(_get_config_setting_value(config_doc, f"{model_key}_config_id"))
    model_name = _normalize_model_name(_get_config_setting_value(config_doc, model_key))
    matched_config = _select_llm_config_from_doc(
        config_doc,
        config_id=config_id,
        model_name=model_name,
    )
    if matched_config is not None:
        return {
            "config_id": _normalize_config_id(matched_config.get("config_id")),
            "model_name": _normalize_model_name(matched_config.get("model_name")),
            "provider": str(matched_config.get("provider") or "").strip().lower(),
        }
    if not config_id and not model_name:
        return None
    return {
        "config_id": config_id,
        "model_name": model_name,
        "provider": None,
    }


def _selection_model_name(selection: Optional[Dict[str, Any]]) -> Optional[str]:
    if not selection:
        return None
    return _normalize_model_name(selection.get("model_name"))


def _selection_config_id(selection: Optional[Dict[str, Any]]) -> Optional[str]:
    if not selection:
        return None
    return _normalize_config_id(selection.get("config_id"))


def _normalize_preferred_models(preferred_models: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if not preferred_models:
        return {}

    normalized: Dict[str, str] = {}
    unified_model = _normalize_model_name(preferred_models.get("model"))
    unified_model_config_id = _normalize_config_id(preferred_models.get("model_config_id"))
    quick_model = _normalize_model_name(preferred_models.get("quick_model"))
    quick_model_config_id = _normalize_config_id(preferred_models.get("quick_model_config_id"))
    deep_model = _normalize_model_name(preferred_models.get("deep_model"))
    deep_model_config_id = _normalize_config_id(preferred_models.get("deep_model_config_id"))

    if unified_model:
        normalized["model"] = unified_model
    if unified_model_config_id:
        normalized["model_config_id"] = unified_model_config_id

    if quick_model:
        normalized["quick_model"] = quick_model
    if quick_model_config_id:
        normalized["quick_model_config_id"] = quick_model_config_id
    if deep_model:
        normalized["deep_model"] = deep_model
    if deep_model_config_id:
        normalized["deep_model_config_id"] = deep_model_config_id

    if unified_model and not quick_model:
        normalized["quick_model"] = unified_model
    if unified_model and not deep_model:
        normalized["deep_model"] = unified_model
    if unified_model_config_id and not quick_model_config_id:
        normalized["quick_model_config_id"] = unified_model_config_id
    if unified_model_config_id and not deep_model_config_id:
        normalized["deep_model_config_id"] = unified_model_config_id

    return normalized


def _get_preferred_assistant_model(preferred_models: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_preferred_models(preferred_models)
    return (
        normalized.get("model")
        or normalized.get("deep_model")
        or normalized.get("quick_model")
    )


def _get_preferred_assistant_config_id(preferred_models: Optional[Dict[str, Any]]) -> Optional[str]:
    normalized = _normalize_preferred_models(preferred_models)
    return (
        normalized.get("model_config_id")
        or normalized.get("deep_model_config_id")
        or normalized.get("quick_model_config_id")
    )


def _build_assistant_model_preferences(
    model: Optional[str] = None,
    model_config_id: Optional[str] = None,
    quick_model: Optional[str] = None,
    quick_model_config_id: Optional[str] = None,
    deep_model: Optional[str] = None,
    deep_model_config_id: Optional[str] = None,
) -> Dict[str, str]:
    normalized = _normalize_preferred_models(
        {
            "model": model,
            "model_config_id": model_config_id,
            "quick_model": quick_model,
            "quick_model_config_id": quick_model_config_id,
            "deep_model": deep_model,
            "deep_model_config_id": deep_model_config_id,
        }
    )
    assistant_model = _get_preferred_assistant_model(normalized)
    assistant_model_config_id = _get_preferred_assistant_config_id(normalized)
    if not assistant_model and not assistant_model_config_id:
        return {}
    preferred: Dict[str, str] = {}
    if assistant_model:
        preferred["model"] = assistant_model
    if assistant_model_config_id:
        preferred["model_config_id"] = assistant_model_config_id
    return preferred


async def _get_llm_config_for_model(
    db,
    target_model: Optional[str],
    target_config_id: Optional[str] = None,
    purpose: str = "",
) -> Optional[LLMConfig]:
    """Get LLM configuration based on model selection, giving priority to config_id, compatible with old model_name."""
    if not target_model and not target_config_id:
        return None
    config_doc = await db.system_configs.find_one(
        {"is_active": True},
        sort=[("version", -1)]
    )
    return resolve_llm_config_from_config_doc(
        config_doc,
        target_model=target_model,
        target_config_id=target_config_id,
        purpose=purpose,
    )


def resolve_llm_config_from_config_doc(
    config_doc: Optional[Dict[str, Any]],
    *,
    target_model: Optional[str],
    target_config_id: Optional[str] = None,
    purpose: str = "",
) -> Optional[LLMConfig]:
    """Unified LLMConfig based on system_configs document parsing for sharing by various subsystems."""
    if not config_doc or "llm_configs" not in config_doc:
        return None

    model_config = _select_llm_config_from_doc(
        config_doc,
        config_id=target_config_id,
        model_name=target_model,
    )
    if model_config is None:
        return None

    resolved_model_name = _normalize_model_name(model_config.get("model_name")) or _normalize_model_name(target_model)
    if not resolved_model_name:
        return None

    from app.services.simple_analysis_service import get_provider_and_url_by_model_sync

    provider_info = get_provider_and_url_by_model_sync(
        resolved_model_name,
        preferred_provider=str(model_config.get("provider") or _get_default_provider(config_doc) or "").strip().lower(),
        preferred_config_id=_normalize_config_id(model_config.get("config_id")) or target_config_id,
    )
    if not provider_info:
        return None

    provider_str = str(model_config.get("provider") or provider_info.get("provider") or "").lower()
    provider_map = {
        "openai": LLMProvider.OPENAI, "deepseek": LLMProvider.DEEPSEEK,
        "dashscope": LLMProvider.DASHSCOPE, "qwen": LLMProvider.DASHSCOPE,
        "zhipu": LLMProvider.ZHIPU, "google": LLMProvider.GOOGLE,
        "anthropic": LLMProvider.ANTHROPIC, "siliconflow": LLMProvider.SILICONFLOW,
        "kimi": LLMProvider.OPENAI, "moonshot": LLMProvider.OPENAI,
        "ollama": LLMProvider.OLLAMA, "openrouter": LLMProvider.OPENROUTER,
    }
    provider = provider_map.get(provider_str, LLMProvider.DASHSCOPE)
    logger.info(
        "[Smart Assistant] Model route analysis: provider=%s model=%s config_id=%s backend_provider=%s",
        provider_str or "unknown",
        resolved_model_name,
        _normalize_config_id(model_config.get("config_id")) or target_config_id or "",
        provider.value,
    )
    return LLMConfig(
        provider=provider, model=resolved_model_name,
        api_key=provider_info.get("api_key"), base_url=provider_info.get("backend_url"),
        temperature=float(model_config.get("temperature", 0.2)),
        max_tokens=int(model_config.get("max_tokens", 4000)),
        timeout=int(model_config.get("timeout", 60)),
        retry_times=int(model_config.get("retry_times", 3)),
    )


def get_system_llm_config_from_config_doc(
    config_doc: Optional[Dict[str, Any]],
    *,
    model_keys: Optional[List[str]] = None,
) -> Optional[LLMConfig]:
    """Parse unified LLMConfig in order of model selection in system settings."""
    if not config_doc or "llm_configs" not in config_doc:
        return None

    resolved_model_keys = model_keys or ["quick_analysis_model", "deep_analysis_model"]
    for model_key in resolved_model_keys:
        selection = _resolve_model_selection(config_doc, model_key)
        if not selection:
            continue

        llm_config = resolve_llm_config_from_config_doc(
            config_doc,
            target_model=_selection_model_name(selection),
            target_config_id=_selection_config_id(selection),
            purpose=model_key,
        )
        if llm_config is not None:
            return llm_config

    for llm_config_doc in config_doc.get("llm_configs") or []:
        if not llm_config_doc.get("enabled", True):
            continue
        llm_config = resolve_llm_config_from_config_doc(
            config_doc,
            target_model=_normalize_model_name(llm_config_doc.get("model_name")),
            target_config_id=_normalize_config_id(llm_config_doc.get("config_id")),
            purpose="first_enabled",
        )
        if llm_config is not None:
            return llm_config

    return None


async def _get_assistant_llm_config(
    db,
    use_reasoning_model: bool = False,
    preferred_models: Optional[Dict[str, Any]] = None,
) -> Optional[LLMConfig]:
    """
    Get the LLM configuration used by the smart assistant from the database
    Prioritize the use of deep thinking model (deep_analysis_model) to ensure accurate reasoning such as time logic and financial report disclosure.
    use_reasoning_model=True When using deep reasoning model (deep_reasoning_model), it is suitable for strategy generation, planning, etc.
    If not configured, fallback to quick model or default model
    """
    config_doc = await db.system_configs.find_one(
        {"is_active": True},
        sort=[("version", -1)]
    )
    if not config_doc or "llm_configs" not in config_doc:
        logger.warning("[Smart Assistant] There is no LLM configuration in the database")
        return None

    llm_configs = config_doc.get("llm_configs", [])
    default_llm = config_doc.get("default_llm")
    quick_selection, deep_selection, reasoning_selection, _ = _resolve_models(config_doc)
    quick_model = _selection_model_name(quick_selection)
    deep_model = _selection_model_name(deep_selection)
    reasoning_model = _selection_model_name(reasoning_selection)
    preferred_assistant_model = _get_preferred_assistant_model(preferred_models)
    preferred_assistant_config_id = _get_preferred_assistant_config_id(preferred_models)
    target_config_id: Optional[str] = None

    if use_reasoning_model and (preferred_assistant_model or preferred_assistant_config_id):
        target_model = preferred_assistant_model
        target_config_id = preferred_assistant_config_id
        logger.info(
            "[Smart Assistant] Use a user-selected helper model: model=%s config_id=%s",
            target_model or "",
            target_config_id or "",
        )
    elif use_reasoning_model and reasoning_selection:
        target_model = _selection_model_name(reasoning_selection)
        target_config_id = _selection_config_id(reasoning_selection)
        logger.info(f"[Smart Assistant] Use deep inference models: {target_model}")
    else:
        target_selection = deep_selection or quick_selection
        target_model = preferred_assistant_model or _selection_model_name(target_selection) or default_llm
        if preferred_assistant_config_id:
            target_config_id = preferred_assistant_config_id
        elif not preferred_assistant_model and target_selection is not None:
            target_config_id = _selection_config_id(target_selection)
        if preferred_assistant_model or preferred_assistant_config_id:
            logger.info(
                "[Smart Assistant] Use a user-selected helper model: model=%s config_id=%s",
                preferred_assistant_model or "",
                preferred_assistant_config_id or "",
            )
        elif deep_selection:
            logger.info(f"[Smart Assistant] Use deep analysis models: {deep_model}")
        elif quick_selection:
            logger.info(f"[Smart Assistant] Deep model is not configured, use fast model: {quick_model}")

    if not target_model:
        target_model = preferred_assistant_model or deep_model or quick_model or default_llm
    if not target_model and llm_configs:
        for cfg in llm_configs:
            if cfg.get("enabled", True):
                target_model = cfg.get("model_name")
                target_config_id = _normalize_config_id(cfg.get("config_id"))
                break

    if not target_model:
        logger.warning("[Smart Assistant] No available model configuration found")
        return None

    return await _get_llm_config_for_model(db, target_model, target_config_id=target_config_id)


async def get_reasoning_llm_config(db=None):
    """
    Obtain deep inference model configuration for policy DSL generation, planning and other scenarios that require strong inference
    Prioritize deep_reasoning_model, fall back to if not configured deep_analysis_model
    """
    from app.core.database import get_mongo_db
    db = db if db is not None else get_mongo_db()
    return await _get_assistant_llm_config(db, use_reasoning_model=True)


async def get_quick_llm_config(db=None):
    """
    Get fast model configuration for low-latency and lightweight judgment scenarios
     (Skill Clarity assessment of requirements dialogue, boundary detection, multiple rounds of responses, etc.)
    """
    from app.core.database import get_mongo_db
    db = db if db is not None else get_mongo_db()
    config_doc = await db.system_configs.find_one(
        {"is_active": True},
        sort=[("version", -1)]
    )
    if not config_doc or "llm_configs" not in config_doc:
        return None
    quick_selection = _resolve_model_selection(config_doc, "quick_analysis_model")
    model_name = _selection_model_name(quick_selection)
    if not model_name:
        return None
    return await _get_llm_config_for_model(
        db,
        model_name,
        target_config_id=_selection_config_id(quick_selection),
    )


async def get_coding_llm_config(db=None):
    """
    Obtain programming model configuration for scenarios such as policy DSL generation that require structured JSON output
    Prioritize coding_model, fall back to if not configured deep_reasoning_model → deep_analysis_model
    """
    from app.core.database import get_mongo_db
    db = db if db is not None else get_mongo_db()
    config_doc = await db.system_configs.find_one(
        {"is_active": True},
        sort=[("version", -1)]
    )
    if not config_doc or "llm_configs" not in config_doc:
        return await get_reasoning_llm_config(db)
    _, deep_selection, reasoning_selection, coding_selection = _resolve_models(config_doc)
    deep_model = _selection_model_name(deep_selection)
    reasoning_model = _selection_model_name(reasoning_selection)
    coding_model = _selection_model_name(coding_selection)
    target_selection = coding_selection or reasoning_selection or deep_selection
    target_model = _selection_model_name(target_selection)
    target_config_id = _selection_config_id(target_selection)
    if target_model:
        logger.info(f"[编程模型] 使用: {target_model} (coding={bool(coding_model)}, reasoning={bool(reasoning_model)})")
    return await _get_llm_config_for_model(db, target_model, target_config_id=target_config_id) if target_model else await get_reasoning_llm_config(db)


class IntelligentAssistantService:
    """智能助手服务"""

    def __init__(
        self,
        db,
        preferred_models: Optional[Dict[str, Any]] = None,
        prefer_reasoning_model: bool = False,
        user_id: str = "",
        assistant_role: str = "general",
        user_context: Optional[dict] = None,
    ):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._openai_tools: Optional[List[Dict[str, Any]]] = None
        self._tool_functions: Optional[Dict[str, Any]] = None
        self._preferred_model = _get_preferred_assistant_model(preferred_models)
        self._preferred_model_config_id = _get_preferred_assistant_config_id(preferred_models)
        self._prefer_reasoning_model = prefer_reasoning_model
        self._user_id = user_id  # Meta-tools for constructing closures with user_id (e.g. remember_this)
        # v3.0 New: Use Q&A robot role related fields
        self._assistant_role = assistant_role or "general"
        self._user_context = user_context or {}

    async def _ensure_client(self) -> bool:
        """Make sure the LLM client and tools are loaded"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(
            self._db,
            use_reasoning_model=self._prefer_reasoning_model,
            preferred_models=_build_assistant_model_preferences(
                model=self._preferred_model,
                model_config_id=self._preferred_model_config_id,
            ) if (self._preferred_model or self._preferred_model_config_id) else None,
        )
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
        except Exception as e:
            logger.error(f"[Smart Assistant] Creating LLM client failed: {e}", exc_info=True)
            return False

        registry = get_tool_registry()
        all_metadata = registry.list_all()

        # v3.0 New: Register only 9 system awareness tools using Q&A bot
        # Do not load financial market data tools, do not load analyst Agent tools
        if self._assistant_role == "usage_helper":
            allowed_tool_ids = {
                "get_user_current_state",
                "get_system_status",
                "get_user_recent_activity",
                "read_user_manual_section",
                "search_user_manual",  # Vector semantic retrieval (new in v3.0.1, solving natural language problem matching)
                "get_data_sync_status",
                "get_paper_trading_status",
                "get_token_usage",
                "get_running_tasks",
            }
            all_metadata = [t for t in all_metadata if t.id in allowed_tool_ids]
            logger.info(f"[Smart Assistant·Use Q&A] Load only {len(all_metadata)} System awareness tools (including vector retrieval/data synchronization/simulated transactions/Token usage/task progress)")

        self._openai_tools = tool_metadata_list_to_openai(all_metadata)

        self._tool_functions = {}
        for tool in all_metadata:
            # Parameterless tools also need to be injected, otherwise they will appear"Tool loaded but unable to execute"
            if tool.fc_enabled:
                func = registry.get_function(tool.id)
                if func:
                    self._tool_functions[tool.id] = func

        # Inject `remember_this` Meta-Tools: Allow users to proactively ask Assistant to remember preferences
        # Reference:docs/05-design/v3.0/unified-memory-layer-mem0.md §15.5 P0-1
        # Use the Q&A bot without injecting remember_this (to avoid polluting the user's long-term memory)
        if self._user_id and self._assistant_role != "usage_helper":
            self._openai_tools.append(_build_remember_this_tool_def())
            self._tool_functions[REMEMBER_THIS_TOOL_NAME] = _make_remember_this_callable(
                self._db, self._user_id,
            )

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(f"[智能助手] 已加载 {len(self._openai_tools)} 个工具")
        return True

    async def _summarize_search_result(
        self,
        tool_text: str,
        user_message: str,
        history_messages: Optional[List[Message]] = None,
        conversation_id: str = "",
    ) -> str:
        """Fast path for recent searches: Submit search results to LLM for targeted summary (shared by chat/chat_stream).

        v3.x Repair: The original implementation of the fast path directly transparently transmits the return value of the search tool to the user, resulting in
        "Asking a question and receiving a list of search links". Search results are now injected into LLM to summarize answers and pass
        Digital traceability line of defense; returning an empty string indicates downgrade (the caller falls back to returning the original search results).
        """
        summarize_messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=(
                    "You are TradingAgents-CN intelligent assistant. The system has performed an online search based on the user s question."
                    "The search results are shown below [return from online search]. Please answer user questions strictly based on this material:\n"
                    "1. Answer the user s question directly and refine the main points. Do not list links or copy the list format of search results;\n"
                    "2. Only use the information that appears in the search results, and do not make up anything that is not in the materials; clearly explain the parts that the materials are not enough to answer;\n"
                    "3. For information involving data/time, indicate the source and date, and pay attention to the timeliness (earlier information should indicate the release time);\n"
                    "4. Distinguish between official confirmation and media reports, and do not describe media reports as official confirmation;\n"
                    "5. When it comes to investment judgment, it only needs to be reminded that it does not constitute investment advice, and there is no need for a lengthy disclaimer."
                ),
            ),
            Message(
                role=MessageRole.SYSTEM,
                content=f"【联网搜索返回】\n{tool_text}",
            ),
        ]
        if history_messages:
            summarize_messages.extend(history_messages)
        summarize_messages.append(
            Message(role=MessageRole.USER, content=user_message.strip())
        )
        try:
            resp = await self._llm_client.achat(summarize_messages)
            await _record_assistant_token_usage(resp, conversation_id or "assistant_chat")
            summarized = (getattr(resp, "content", "") or "").strip()
        except Exception as sum_err:
            logger.warning(f"[Smart Assistant] Search results LLM summary failed, downgraded to return to original results: {sum_err}")
            return ""
        if not summarized:
            return ""
        # Digital traceability line of defense: The numbers in the summary must be traceable to the original text of the search results
        fast_tool_results = [{"tool": "search_recent_information", "content": tool_text}]
        if _has_fabricated_tool_json(summarized) or _has_untraced_risky_numbers(
            summarized,
            fast_tool_results,
            ["search_recent_information"],
            user_message,
            [],
        ):
            logger.warning("[Smart Assistant] The fast path summary has not passed the traceability verification and is downgraded to return to the original search results.")
            return ""
        return summarized

    def _build_tool_interceptor(self, conversation_id: str):
        """Build HITL tool interceptor (v3.6.0: extracted as class method, shared by chat/chat_stream).

        For key operations (trigger analysis/delete configuration, etc.), first save pending to MongoDB,
        Let the user confirm before executing to prevent LLM from bypassing confirmation and executing directly in the streaming/non-streaming path.
        """
        async def _intercept(tool_call) -> Optional[Any]:
            from core.hitl.assistant_hitl import (
                is_critical_tool,
                save_pending_critical_action,
                build_pending_confirmation_reply,
            )

            tool_id = tool_call.name
            if not is_critical_tool(tool_id):
                return None

            pending_id = await save_pending_critical_action(
                self._db,
                user_id=self._user_id or "default",
                conversation_id=conversation_id or "default",
                tool_id=tool_id,
                tool_arguments=tool_call.arguments,
            )
            if not pending_id:
                # Downgrade to direct execution when saving fails
                return None

            confirmation_msg = build_pending_confirmation_reply(
                tool_id=tool_id,
                tool_arguments=tool_call.arguments,
                pending_id=pending_id,
            )
            # Returns ToolResult (compatible with unified LLM client)
            from core.llm.unified_client import ToolResult
            return ToolResult(
                tool_call_id=tool_call.id,
                name=tool_id,
                content=confirmation_msg,
                is_error=False,
            )
        return _intercept

    # ─────────────────────────────────────────────────────────────────────
    # A11 Phase 3: Unified routing pipeline.chat() (JSON) with chat_stream() (SSE) Just
    # The same set of "path registry" → ReplyGate → The two output adapters for the "Result" pipeline,
    # No longer maintain separate parallel implementations of HITL/fast path/precheck/tool loop/quality defense lines (S2).
    # ─────────────────────────────────────────────────────────────────────

    @staticmethod
    def _effective_timeout(tools_used: List[str]) -> int:
        """The total timeout is dynamically calculated based on the tier of the invoked tool (common to both modes)."""
        base = ASSISTANT_TIMEOUT_SECONDS
        if not tools_used:
            return base
        try:
            from core.tools import get_tool_registry
            from core.tools.config import ToolTimeoutTier
            registry = get_tool_registry()
            for name in tools_used:
                meta = registry.get(name)
                if meta and getattr(meta, "timeout_tier", "") == ToolTimeoutTier.HEAVY:
                    return base + ASSISTANT_HEAVY_TOOL_EXTRA_SECONDS
        except Exception:
            pass
        return base

    async def _route_candidate(self, req: AssistantRequest) -> ReplyCandidate:
        """Path registries are assembled and executed in explicit priority; the first path hit wins."""
        registry = (
            PathRegistry()
            .register(
                ROUTE_HITL, PRIORITY_HITL, self._path_hitl,
                route_type=ROUTE_TYPE_PASSTHROUGH, description="HITL Confirm/deny pending action",
            )
            .register(
                ROUTE_UNSUPPORTED_ASSET, PRIORITY_UNSUPPORTED_ASSET, self._path_unsupported_asset,
                route_type=ROUTE_TYPE_PASSTHROUGH, description="不支持品种拦截",
            )
            .register(
                ROUTE_LLM_UNAVAILABLE, PRIORITY_LLM_UNAVAILABLE, self._path_llm_unavailable,
                route_type=ROUTE_TYPE_PASSTHROUGH, description="LLM 客户端不可用",
            )
            .register(
                ROUTE_FAST_SEARCH, PRIORITY_FAST_SEARCH, self._path_fast_search,
                route_type=ROUTE_TYPE_ANSWER, description="Recent search fast paths (LLM summary)",
            )
            .register(
                ROUTE_DATA_PRECHECK, PRIORITY_DATA_PRECHECK, self._path_data_precheck,
                route_type=ROUTE_TYPE_PASSTHROUGH, description="数据同步预检查",
            )
            .register(
                ROUTE_MAIN_LLM, PRIORITY_MAIN_LLM, self._path_main_llm,
                route_type=ROUTE_TYPE_ANSWER, description="LLM + Tool cycle main path",
            )
        )
        return await registry.resolve(req)

    async def _path_hitl(
        self, req: AssistantRequest
    ) -> Optional[ReplyCandidate]:
        """Path 1: HITL confirmation/rejection resolution of pending operations (passthrough registration path)."""
        try:
            from core.hitl.assistant_hitl import try_resolve_pending_action
            resolution = await try_resolve_pending_action(
                self._db,
                user_id=self._user_id or "default",
                conversation_id=req.conversation_id or "default",
                user_message=req.user_message,
            )
        except Exception as e:
            logger.warning("[Smart Assistant] HITL Check failed (downgraded to normal conversation): %s", e)
            return None
        if not resolution:
            return None
        if resolution.get("type") == "confirmed":
            result_text = resolution.get("result", "") or "操作已执行完成"
            return ReplyCandidate.passthrough(
                reply=f"✅ Confirmed execution:{result_text}",
                route_id=ROUTE_HITL,
                tools_used=[resolution.get("tool_id", "")],
            )
        if resolution.get("type") == "rejected":
            return ReplyCandidate.passthrough(
                reply=resolution.get("message", "已取消操作"),
                route_id=ROUTE_HITL,
            )
        return None

    async def _path_unsupported_asset(
        self, req: AssistantRequest
    ) -> Optional[ReplyCandidate]:
        """Path 2: The product type (Hong Kong stocks/US stocks, etc.) is not supported. System prompts (vocabulary fact source: lexicon)."""
        message = detect_unsupported_asset(req.user_message)
        if not message:
            return None
        return ReplyCandidate.passthrough(
            reply=message, route_id=ROUTE_UNSUPPORTED_ASSET
        )

    async def _path_llm_unavailable(
        self, req: AssistantRequest
    ) -> Optional[ReplyCandidate]:
        """Path 3: The LLM client cannot be initialized (missing configuration, etc.)."""
        if await self._ensure_client():
            return None
        logger.warning("[Smart Assistant] LLM Client creation failed")
        return ReplyCandidate.passthrough(
            reply="The smart assistant is temporarily unavailable. Please check whether the LLM configuration has been configured correctly in Settings.",
            route_id=ROUTE_LLM_UNAVAILABLE,
        )

    async def _path_fast_search(
        self, req: AssistantRequest
    ) -> Optional[ReplyCandidate]:
        """Path 4:"latest/recent"quasi-factual question → Recent searches + LLM Targeted summary (answer type).

        LLM The mark llm_processed is only allowed when the summary is successful; when it fails, it will be intercepted by the gate contract and downgraded to
        "Limitations+Excerpts of evidence", Both modes will no longer transparently transmit the search link list.
        """
        if not _should_use_recent_search(req.user_message):
            return None
        # For problems that dedicated external skills can handle in a structured manner (such as car model sales database), the fast path must give way.——
        # Otherwise "recently+"Variation" keyword combination will hijack the question to a web search before the LLM tool selects it.
        # Special tools don't even have a chance to appear. Matching is based on registry metadata and does not hard-code specific skills.
        if _matches_generated_skill(req.user_message):
            logger.info("[Smart Assistant] If a recent search keyword is hit but a dedicated Skill exists, switch to the regular tool selection path.")
            return None
        try:
            from core.tools.implementations.assistant_ops.recent_search import (
                run_recent_information_search,
            )

            tool_result = run_recent_information_search(req.user_message.strip())
            if inspect.isawaitable(tool_result):
                tool_result = await tool_result
            tool_text = str(tool_result or "").strip()
            if not tool_text:
                return None
            logger.info("[Smart Assistant] Hit the recent search fast path, and the search results will be summarized and answered by LLM")
            summarized = await self._summarize_search_result(
                tool_text, req.user_message, req.history_messages, req.conversation_id,
            )
            return ReplyCandidate.answer(
                reply=summarized or tool_text,
                route_id=ROUTE_FAST_SEARCH,
                llm_processed=bool(summarized),
                tools_used=["search_recent_information"],
                evidence=[
                    Evidence(
                        source_type=EVIDENCE_SEARCH,
                        source_id="search_recent_information",
                        content=tool_text,
                    )
                ],
            )
        except Exception as e:
            logger.warning("[Smart Assistant] The recent search for a fast path failed and fell back to the regular conversation.: %s", e)
            return None

    async def _build_data_precheck_message(self, user_message: str) -> Optional[str]:
        """Data synchronization pre-check: return the guidance copy when the data is insufficient, return None when the data is sufficient/irrelevant."""
        stock_code = _extract_stock_code(user_message)
        if not stock_code:
            text_lower = user_message.lower()
            if any(k in text_lower for k in _STOCK_DATA_KEYWORDS):
                stock_code = await _resolve_stock_name_to_code(user_message, db=self._db)
                logger.info("[Smart Assistant] pre-check·Name resolution results: %s", stock_code)
        if not stock_code:
            return None

        text_lower = user_message.lower()
        if not any(k in text_lower for k in _STOCK_DATA_KEYWORDS):
            return None

        sync_status = await _check_stock_data_sync(stock_code, db=self._db)
        logger.info("[Smart Assistant] pre-check·Stock %s data status: %s", stock_code, sync_status)
        if not sync_status or sync_status.get("error"):
            return None

        has_hist = sync_status.get("has_historical", False)
        has_fin = sync_status.get("has_financial", False)
        has_basic = sync_status.get("has_basic", False)
        hist_records = sync_status.get("hist_records", 0)
        fin_records = sync_status.get("fin_records", 0)

        financial_keywords = [
            "财报", "利润", "营收", "收入", "净利润", "毛利率", "现金流",
            "资产", "负债", "估值", "市盈率", "市净率", "pe", "pb", "ps",
            "盈利", "财务", "roe", "roa", "资产负债率",
        ]
        technical_keywords = [
            "技术面", "技术指标", "macd", "rsi", "kdj", "boll", "布林",
            "均线", "ma", "ema", "超买", "超卖", "背离", "支撑", "阻力",
            "压力位", "趋势", "k线",
        ]
        investment_decision_keywords = [
            "入手", "买入", "卖出", "加仓", "减仓", "持有", "清仓",
            "值得", "能不能买", "该不该", "怎么样", "如何", "分析",
        ]
        asks_financial = any(k in text_lower for k in financial_keywords)
        asks_technical = any(k in text_lower for k in technical_keywords)
        asks_investment_decision = any(k in text_lower for k in investment_decision_keywords)
        # Investment decision-making problems require financial+Comprehensive technical judgment
        if asks_investment_decision:
            asks_financial = True
            asks_technical = True

        missing_parts = []
        if asks_financial and not has_fin:
            missing_parts.append("Financial data (income statement/balance sheet/cash flow statement, currently 0 items)")
        if asks_technical and (not has_hist or hist_records < 30):
            missing_parts.append(f"历史行情数据（当前 {hist_records} 条，技术分析需要至少 30 条）")
        if not missing_parts:
            return None

        missing_text = "\n".join(f"• ❌ {p}" for p in missing_parts)
        available_text = (
            f"• ✅ 历史行情: {hist_records} 条"
            if has_hist else "• ❌ Historical Quotes: Not synced"
        )
        available_text += "\n"
        available_text += (
            f"• ✅ 财务数据: {fin_records} 条"
            if has_fin else "• ❌ financial data: Not synced"
        )
        available_text += "\n"
        available_text += "✅ 基础数据: 已同步" if has_basic else "❌ 基础数据: 未同步"

        logger.info(
            "[Smart Assistant] Insufficient data for stock %s, interception (missing: %s) ",
            stock_code, ", ".join(missing_parts),
        )
        return (
            f"📊 股票 {stock_code} 的数据不充分，无法进行分析\n\n"
            f"Current data synchronization status:\n{available_text}\n\n"
            f"Missing data:\n{missing_text}\n\n"
            f"Please synchronize data first before asking questions:\n"
            f"• Go to the Data Management page and search {stock_code} and trigger data synchronization\n"
            f"• It is recommended to synchronize complete historical market prices (at least 250 trading days) and financial data\n"
            f"• After the synchronization is completed, ask again and I will call the tool to obtain real data for you to analyze.\n\n"
            f"Or if you just want to know what s publicly available on the internet, I can also search via web_search."
            f"Do you need me to search?"
        )

    async def _path_data_precheck(
        self, req: AssistantRequest
    ) -> Optional[ReplyCandidate]:
        """Path 5: Guidance prompt when stock data is not synchronized (passthrough registration path)."""
        message = await self._build_data_precheck_message(req.user_message)
        if not message:
            return None
        return ReplyCandidate.passthrough(
            reply=message,
            route_id=ROUTE_DATA_PRECHECK,
            tools_used=["get_data_sync_status"],
        )

    async def _path_main_llm(self, req: AssistantRequest) -> ReplyCandidate:
        """Path 6 (Default): RAG/Memory Injection + LLM tool cycle + Four lines of defense (answer type).

        Quality processing sequence (unified for both modes):
        ① _do_chat The internal automatic error correction for unsourced / untraced can be repeated at most once;
        ② After constructing the answer candidate, the adapter will unify it and pass it through the ReplyGate export;
        ③ If it still fails, it will be downgraded to fallback_evidence (limitation description+Excerpts from the evidence).
        Data transparency annotations are transparently transmitted through meta and appended by the adapter after the gate to avoid annotation numbers interfering with the check.
        """
        user_message = req.user_message
        conversation_id = req.conversation_id

        # RAG Dynamic knowledge retrieval (graceful degradation: returns empty string when unavailable)
        knowledge_snippets = ""
        try:
            from core.knowledge import FinancialKnowledgeManager
            km = FinancialKnowledgeManager(db=self._db)
            knowledge_snippets = km.retrieve_for_prompt(user_message)
            if knowledge_snippets:
                logger.info("[Smart Assistant] ✅ RAG Knowledge retrieval successful (%d character)", len(knowledge_snippets))
            else:
                logger.info("[Smart Assistant] RAG Knowledge retrieval returns empty (no matching knowledge)")
        except Exception as e:
            logger.warning("[Smart Assistant] ⚠️ Knowledge retrieval failed (downgraded to static knowledge): %s", e)

        # Fact memory retrieval: reuse real data obtained by previous tools across sessions (time-tagged, injected only if it has not expired)
        recalled_memory_docs: List[Dict[str, Any]] = []
        memory_injection = ""
        try:
            recalled_memory_docs = await _recall_memory_facts(
                self._db, user_message, conversation_id or ""
            )
            memory_injection = _build_memory_injection(recalled_memory_docs)
        except Exception as e:
            logger.warning("[Smart Assistant] Abnormal factual memory retrieval (ignored): %s", e)

        messages = [
            Message(
                role=MessageRole.SYSTEM,
                content=_get_system_prompt(
                    knowledge_snippets,
                    req.assistant_settings,
                    is_im=req.is_im,
                    user_profile=req.user_profile,
                    current_topic_title=req.current_topic_title,
                    memory_block=req.memory_block,
                    assistant_role=self._assistant_role,
                    user_context=self._user_context,
                ),
            ),
        ]
        if memory_injection:
            messages.append(Message(role=MessageRole.SYSTEM, content=memory_injection))
        if req.history_messages:
            messages.extend(req.history_messages)
            logger.info("[Smart Assistant] %d historical messages have been injected", len(req.history_messages))
        messages.append(Message(role=MessageRole.USER, content=user_message.strip()))

        # Tracing Trusted Text: Conversation History Tool Returns + Injected factual memory (quoting memorized numbers does not count as fabrication)
        memory_trusted_contents = [
            str(d.get("content", "")) for d in recalled_memory_docs if d.get("content")
        ]

        tools_used: List[str] = req.tools_used
        tool_results: List[Dict[str, Any]] = []
        # Quality signal (S9 buried point): defense trigger/retry record, eventually dropped with candidate.meta
        quality_signals: List[str] = []

        async def _emit_progress(payload: Dict[str, Any]) -> None:
            if req.on_progress is None:
                return
            try:
                await req.on_progress(payload)
            except Exception:
                pass

        async def _do_chat(_retry_attempt: int = 0) -> str:
            tool_interceptor = self._build_tool_interceptor(conversation_id or "default")
            achat_kwargs: Dict[str, Any] = dict(
                tools=self._openai_tools,
                auto_execute_tools=True,
                max_tool_rounds=8,
                tools_used=tools_used,
                tool_results_collector=tool_results,
                dry_run=False,
                tool_interceptor=tool_interceptor,
            )
            # Only streaming mode injects progress callbacks (tool_started / tool_completed and other events)
            if req.on_progress is not None:
                achat_kwargs["progress_callback"] = req.on_progress
                # The first round of LLM thinking may last several minutes (inference model+Large tool table+long history),
                # Send a feedback first to avoid users waiting silently without any prompts.
                await _emit_progress({
                    "event": "llm_thinking",
                    "round": 1,
                    "message": "Analyzing the problem and planning steps to deal with it…",
                })

            resp = await self._llm_client.achat(messages, **achat_kwargs)
            await _record_assistant_token_usage(resp, conversation_id or "assistant_chat")

            # Bottom line:"Tools should be taken"When the personal data query is not adjusted in the first round, the second forced boot
            if not tools_used and _should_force_tool_retry(user_message):
                quality_signals.append("forced_tool_retry")
                logger.warning("[Smart Assistant] The tool was not called in the first round, and the tool was triggered to try again.")
                retry_messages = list(messages)
                retry_messages.append(Message(
                    role=MessageRole.USER,
                    content=(
                        "Please do not guess or make up results based directly on context."
                        "Such questions must first call relevant tools to obtain real data, and then return answers based on the tools."
                        "In particular, you cannot directly make up real-time numbers such as index points, rise and fall, MACD, RSI, moving averages, trading volume, etc."
                        "If the tool returns empty or the date does not match, then clearly indicate that the data is empty or the data date does not match."
                    ),
                ))
                # Priority tool_choice=required; If the model side does not support it, downgrade it to normal and try again.
                retry_kwargs = dict(achat_kwargs)
                retry_kwargs["tool_choice"] = "required"
                try:
                    resp = await self._llm_client.achat(retry_messages, **retry_kwargs)
                    await _record_assistant_token_usage(resp, conversation_id or "assistant_chat")
                except Exception as retry_err:
                    logger.warning("[Smart Assistant] tool_choice=required Retry failed, downgrade to normal and try again: %s", retry_err)
                    resp = await self._llm_client.achat(retry_messages, **achat_kwargs)
                    await _record_assistant_token_usage(resp, conversation_id or "assistant_chat")

            # Fact memory preservation: extracted in this round"facts"Drop library (with time tag, reused across sessions)
            if tool_results:
                await _persist_memory_facts(
                    self._db,
                    tool_results,
                    user_message,
                    conversation_id or "",
                    assistant_reply=resp.content or "",
                    related_context=_recent_user_context(messages),
                )

            # ── Reply to the last four lines of defense (p.① Downgrade: Feedback and reanswer, up to 1 time)──
            reply_content = resp.content or ""
            trusted_texts = _extract_history_tool_contents(messages) + memory_trusted_contents

            if _has_fabricated_tool_json(reply_content):
                quality_signals.append("fabricated_json")
                logger.warning("[Smart Assistant] Fabricated tool JSON result detected, hard intercepted reply")
                return (
                    "Sorry, there was a format error when I presented the tool return result (I rewritten the tool return into structured data),"
                    "This can lead to data distortion.\n\n"
                    "Please ask again and I will present you the analysis results strictly according to the original content returned by the tool."
                )
            if _has_fabricated_tool_refs(reply_content, tools_used):
                quality_signals.append("fabricated_refs")
                logger.warning("[Smart Assistant] Traces of forged tool calls were detected and replies were intercepted (tools_used=%s) ", tools_used)
                return (
                    "Sorry, I encountered a data source annotation error when generating my response.\n\n"
                    "To make sure you re getting reliable information, try breaking down your questions to be more specific."
                    "For example, directly specify the data dimension you want to view (such as\"Check out the latest financial report of Muyuan Shares\"\"Look at technical indicators\"etc.),"
                    "I will call the corresponding tools to obtain real data and then analyze it for you."
                )
            if _has_unsourced_numbers(reply_content, tools_used):
                logger.warning(
                    "[Smart Assistant] An untuned tool is detected but the reply contains a large number of numbers. Intercept the reply (number of numbers).=%d) ",
                    len(_SPECIFIC_NUMBER_RE.findall(reply_content)),
                )
                if _retry_attempt < 1:
                    quality_signals.append("unsourced_retry")
                    await _emit_progress({
                        "event": "progress",
                        "stage": "retry",
                        "message": "Unverified data detected and tool is being called to re-obtain it…",
                    })
                    messages.append(_retry_message("assistant", reply_content))
                    messages.append(_retry_message("user", _UNSOURCED_RETRY_PROMPT))
                    logger.info("[Smart Assistant] Untraced digital reply intercepted, automatic error correction and retry (first time)")
                    return await _do_chat(_retry_attempt + 1)
                quality_signals.append("unsourced_blocked")
                return (
                    "Sorry, I failed to call the tool to obtain real data twice just now. I have stopped answering to avoid misleading.\n\n"
                    "Please ask a more specific question (e.g. specify an industry or stock, e.g.\"What is the recent trend of the breeding industry?\") , "
                    "I will first call the tool to obtain real data and then analyze it for you."
                )
            if _has_untraced_risky_numbers(
                reply_content, tool_results, tools_used,
                user_message, trusted_texts,
            ):
                logger.warning("[Smart Assistant] Untraceable high-risk numbers detected (suspected training memory filling/unit conversion errors), intercepted reply")
                if _retry_attempt < 1:
                    quality_signals.append("untraced_retry")
                    await _emit_progress({
                        "event": "progress",
                        "stage": "retry",
                        "message": "Untraceable number detected, regenerating based on tool data…",
                    })
                    untraced_numbers = _get_untraced_risky_numbers(
                        reply_content, tool_results, user_message, trusted_texts
                    )[:6]
                    retry_prompt = _UNTRACED_RETRY_PROMPT_TEMPLATE.format(
                        numbers="、".join(untraced_numbers)
                    )
                    messages.append(_retry_message("assistant", reply_content))
                    messages.append(_retry_message("user", retry_prompt))
                    logger.info("[Smart Assistant] Intercepted digital reply that cannot be traced, automatic error correction and retry (first time)")
                    return await _do_chat(_retry_attempt + 1)
                quality_signals.append("untraced_blocked")
                untraced_detail = "、".join(_get_untraced_risky_numbers(
                    reply_content, tool_results, user_message, trusted_texts
                )[:6])
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

            return reply_content

        content = await asyncio.wait_for(
            _do_chat(), timeout=self._effective_timeout(tools_used)
        )
        reply = content or "Sorry, the answer cannot be generated at the moment, please try again later."
        if tools_used:
            logger.info("[Smart Assistant] Tool called: %s", tools_used)
        else:
            logger.info("[Smart Assistant] No tools invoked (plain text reply)")
        logger.info("[Smart Assistant] Reply content(first 200 words): %s", reply[:200])

        # Evidence set: tool return for this round (skipping is_error)+ Injected fact memory
        evidence = [
            Evidence(
                source_type=EVIDENCE_TOOL,
                source_id=str(item.get("tool") or "tool"),
                content=str(item.get("content") or ""),
            )
            for item in tool_results
            if item.get("content") and not item.get("is_error")
        ]
        evidence.extend(
            Evidence(source_type=EVIDENCE_MEMORY, source_id="mem0", content=trusted_text)
            for trusted_text in memory_trusted_contents
            if trusted_text
        )

        # Transparency Notes (Derivations/Estimates↔The original value of the tool) is transparently transmitted through meta, and is appended by the adapter after passing the gate.
        meta: Dict[str, Any] = {}
        if quality_signals:
            meta["quality_signals"] = quality_signals
        if tools_used:
            note = _build_data_transparency_note(
                reply, tool_results, user_message,
                _extract_history_tool_contents(messages) + memory_trusted_contents,
            )
            if note:
                meta["transparency_note"] = note

        return ReplyCandidate.answer(
            reply=reply,
            route_id=ROUTE_MAIN_LLM,
            llm_processed=True,
            tools_used=tools_used,
            evidence=evidence,
            meta=meta,
        )

    def _through_gate(
        self, candidate: ReplyCandidate, req: AssistantRequest
    ) -> ReplyCandidate:
        """The only quality export (common to both modes): Contract + Four lines of defense; answer failure fallback evidence.

        Level result writing meta["gate"] (S9 Buried in the adapter for unified collection).
        """
        trusted = (
            _extract_history_tool_contents(req.history_messages)
            if req.history_messages else []
        )
        result = ReplyGate().run(candidate, req.user_message, trusted)
        if not result.passed and candidate.route_type == ROUTE_TYPE_ANSWER:
            logger.warning("[Smart Assistant] gate Exit interception, fallback evidence: %s", result.failed_checks)
            fallback = build_fallback_candidate(candidate, result.failures)
            fallback.meta["gate"] = {
                "passed": False,
                "failed": list(result.failed_checks),
                "fallback": True,
            }
            candidate = fallback
        elif not result.passed:
            # passthrough Failure to register is a procedural defect (it should not happen normally). It is only recorded and does not make up a reply.
            logger.error("[Smart Assistant] passthrough The path is not registered: %s", result.failed_checks)
            candidate.meta["gate"] = {
                "passed": False,
                "failed": list(result.failed_checks),
                "fallback": False,
            }
        else:
            candidate.meta["gate"] = {"passed": True, "failed": [], "fallback": False}
        return candidate

    def _finalize_result(
        self, candidate: ReplyCandidate, req: AssistantRequest
    ) -> Dict[str, Any]:
        """The unified return structure after the level; transparent annotations are added here (not involved in gate checking)."""
        reply = candidate.reply
        note = candidate.meta.get("transparency_note")
        if note and not reply.endswith(note):
            reply = reply + note
        return {
            "reply": reply,
            "tools_used": candidate.tools_used,
            "data_refs": extract_data_refs(candidate.evidence),
        }

    def _record_metrics(
        self,
        result: Dict[str, Any],
        candidate: ReplyCandidate,
        req: AssistantRequest,
        t0: float,
        streaming: bool,
        error: Optional[str] = None,
    ) -> None:
        """S9 Quality focus: one event per conversation round (fire-and-forget, never affecting the main link)."""
        try:
            meta = candidate.meta or {}
            gate = meta.get("gate") or {}
            quality_metrics.record(
                db=self._db,
                streaming=streaming,
                conversation_id=req.conversation_id,
                user_id=self._user_id,
                message_preview=(req.user_message or "")[:120],
                route_id=candidate.route_id,
                route_priority=meta.get("route_priority"),
                route_type=candidate.route_type,
                llm_processed=candidate.llm_processed,
                gate_passed=gate.get("passed"),
                gate_failed=gate.get("failed") or [],
                fallback_used=bool(gate.get("fallback")),
                quality_signals=meta.get("quality_signals") or [],
                evidence_count=len(candidate.evidence),
                data_refs_count=len(result.get("data_refs") or []),
                reply_chars=len(result.get("reply") or ""),
                tools_used=result.get("tools_used") or [],
                duration_ms=int((time.monotonic() - t0) * 1000),
                error=error,
            )
        except Exception as exc:  # Failure to bury the assembly point will not affect the dialogue.
            logger.debug("[Smart Assistant] Quality buried point assembly failed (ignored): %s", exc)

    async def chat(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        assistant_settings: dict = None,
        is_im: bool = False,
        history_messages: Optional[List[Message]] = None,
        user_profile: Optional[dict] = None,
        current_topic_title: Optional[str] = None,
        memory_block: str = "",
    ) -> Dict[str, Any]:
        """Assistant conversation (non-streaming/JSON output adapter).

        with chat_stream() The registry and ReplyGate share the same path, only the output form is different.

        Returns:
            {"reply": str, "tools_used": List[str], "data_refs": List[dict]}
        """
        t0 = time.monotonic()
        resolved_user_message = _rewrite_number_selection_reply(user_message, history_messages)

        req = AssistantRequest(
            service=self,
            user_message=resolved_user_message,
            conversation_id=conversation_id,
            assistant_settings=assistant_settings,
            is_im=is_im,
            history_messages=history_messages,
            user_profile=user_profile,
            current_topic_title=current_topic_title,
            memory_block=memory_block,
        )

        try:
            candidate = await self._route_candidate(req)
        except asyncio.TimeoutError:
            timeout_used = self._effective_timeout(req.tools_used)
            logger.warning("[Smart Assistant] Request timeout (%ss)", timeout_used)
            candidate = ReplyCandidate.passthrough(
                reply=(
                    f"Sorry, it took too long to process your issue (more than {timeout_used} seconds), has been interrupted.\n\n"
                    "Common cause: The model is processing a more complex analysis (multiple rounds of tool calls+Think long).\n"
                    "It is recommended that you:\n"
                    "• If the result table has been generated in the previous dialogue, you can directly request\"Export the table just now as Excel\" (Completed in seconds)\n"
                    "• Try to break the question down into more specifics\n"
                    "• Try again later"
                ),
                route_id=ROUTE_TIMEOUT,
                tools_used=req.tools_used,
            )
        except Exception as e:
            logger.exception("[智能助手] 对话失败")
            candidate = ReplyCandidate.passthrough(
                reply=f"An error occurred while processing your request:{str(e)}. Please check the network and LLM configuration and try again.",
                route_id=ROUTE_ERROR,
                tools_used=req.tools_used,
            )

        candidate = self._through_gate(candidate, req)
        result = self._finalize_result(candidate, req)
        self._record_metrics(result, candidate, req, t0, streaming=False)
        return result

    async def chat_stream(
        self,
        user_message: str,
        conversation_id: Optional[str] = None,
        assistant_settings: dict = None,
        is_im: bool = False,
        history_messages: Optional[List[Message]] = None,
        user_profile: Optional[dict] = None,
        current_topic_title: Optional[str] = None,
        memory_block: str = "",
    ) -> AsyncGenerator[str, None]:
        """Smart Assistant Conversations (Streaming/SSE Output Adapter).

        with chat() Sharing the same path to the registry with ReplyGate: forwarding during tool execution progress
        event (tool_started/tool_completed/retry/keepalive), and finally reply to the entire generation,
        After passing the gate, it is cut into pieces according to the fixed block size and pushed (the LLM call itself is non-streaming, so the level can
        Performed on full reply before any bytes are emitted, does not exist"token Pushed"dilemma).
        done Event payload:{"tools_used": [...], "data_refs": [...]}. 
        """

        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

        t0 = time.monotonic()
        resolved_user_message = _rewrite_number_selection_reply(user_message, history_messages)
        logger.info("[Smart Assistant·streaming] chat_stream start,user_message=%r", resolved_user_message[:50])

        req = AssistantRequest(
            service=self,
            user_message=resolved_user_message,
            conversation_id=conversation_id,
            assistant_settings=assistant_settings,
            is_im=is_im,
            history_messages=history_messages,
            user_profile=user_profile,
            current_topic_title=current_topic_title,
            memory_block=memory_block,
        )

        event_queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue()

        async def _progress(payload: Dict[str, Any]) -> None:
            await event_queue.put(payload)

        req.on_progress = _progress
        task = asyncio.create_task(self._route_candidate(req))

        try:
            # During pipeline execution, tool progress events are continuously forwarded, and a heartbeat occurs when there is no event within 1 second.
            while not task.done():
                try:
                    payload = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                    yield _sse(payload.get("event", "progress"), payload)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue

            while not event_queue.empty():
                payload = event_queue.get_nowait()
                yield _sse(payload.get("event", "progress"), payload)

            candidate = task.result()
            candidate = self._through_gate(candidate, req)
            result = self._finalize_result(candidate, req)
            self._record_metrics(result, candidate, req, t0, streaming=True)
            reply = result["reply"]

            # The entire segment is cut into pieces after passing through the gate, maintaining the front-end rendering experience segment by segment.
            chunk_size = 40
            for i in range(0, len(reply), chunk_size):
                yield _sse("token", {"content": reply[i:i + chunk_size]})
                await asyncio.sleep(0.015)

            yield _sse("done", {
                "tools_used": result["tools_used"],
                "data_refs": result["data_refs"],
            })
        except asyncio.CancelledError:
            if not task.done():
                task.cancel()
            self._record_metrics(
                {"tools_used": req.tools_used, "data_refs": [], "reply": ""},
                ReplyCandidate.passthrough("", route_id="cancelled"),
                req, t0, streaming=True, error="cancelled",
            )
            yield _sse("error", {"message": "请求已取消"})
            yield _sse("done", {"tools_used": req.tools_used, "error": True})
        except asyncio.TimeoutError:
            timeout_used = self._effective_timeout(req.tools_used)
            logger.warning("[Smart Assistant·streaming] Request timeout (%ss)", timeout_used)
            self._record_metrics(
                {"tools_used": req.tools_used, "data_refs": [], "reply": ""},
                ReplyCandidate.passthrough("", route_id=ROUTE_TIMEOUT),
                req, t0, streaming=True, error=f"timeout:{timeout_used}s",
            )
            yield _sse("error", {"message": f"处理超时（已超过 {timeout_used} 秒）。若对话中已生成过结果表格，可直接要求导出成 Excel；或稍后重试。"})
            yield _sse("done", {"tools_used": req.tools_used, "error": True})
        except Exception as e:
            logger.exception("[Smart Assistant·streaming] Conversation failed")
            self._record_metrics(
                {"tools_used": req.tools_used, "data_refs": [], "reply": ""},
                ReplyCandidate.passthrough("", route_id=ROUTE_ERROR),
                req, t0, streaming=True, error=str(e)[:200],
            )
            yield _sse("error", {"message": f"An error occurred while processing the request:{str(e)}"})
            yield _sse("done", {"tools_used": req.tools_used, "error": True})



def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _generate_thread_id() -> str:
    return f"thr_{uuid.uuid4().hex[:12]}"


def _normalize_thread_title(title: str) -> str:
    text = (title or "").strip().lower()
    if not text:
        return ""

    replacements = {
        "新能源汽车": "新能源车",
        "新能源汽車": "新能源车",
        "个股": "公司",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)

    for token in ["（", "）", "(", ")", "-", "_", " ", "　", "/", "\\", "·", "、"]:
        text = text.replace(token, "")

    removable_suffixes = [
        "研究主题",
        "产业链研究",
        "行业研究",
        "板块研究",
        "公司研究",
        "个股研究",
        "深度研究",
        "专题研究",
        "课题研究",
        "产业链",
        "行业",
        "板块",
        "研究",
        "分析",
        "跟踪",
        "专题",
        "主题",
    ]
    changed = True
    while changed and len(text) > 2:
        changed = False
        for suffix in removable_suffixes:
            if text.endswith(suffix) and len(text) > len(suffix) + 1:
                text = text[: -len(suffix)]
                changed = True
                break

    return text


def _thread_titles_match(first: str, second: str) -> bool:
    normalized_first = _normalize_thread_title(first)
    normalized_second = _normalize_thread_title(second)
    if not normalized_first or not normalized_second:
        return False
    return normalized_first == normalized_second


def _find_similar_thread(
    docs: List[Dict[str, Any]],
    title: str,
    parent_thread_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    normalized_parent_id = (parent_thread_id or "").strip() or None
    candidates = [
        doc for doc in docs
        if (doc.get("parent_thread_id") or None) == normalized_parent_id
    ]
    for doc in candidates:
        if _thread_titles_match(doc.get("title") or "", title):
            return doc
    return None


def _is_external_session_thread_id(thread_id: Optional[str]) -> bool:
    return bool(thread_id and ":" in thread_id)


def _is_visible_assistant_topic(doc: Dict[str, Any]) -> bool:
    if doc.get("archived") is True:
        return False
    if (doc.get("topic_type") or "") == "im_session":
        return False
    return not _is_external_session_thread_id(doc.get("thread_id"))


def _sanitize_thread_summary(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not summary:
        return None

    abstract = str(summary.get("abstract") or "").strip()
    confirmed_facts = summary.get("confirmed_facts") or []
    open_questions = summary.get("open_questions") or []
    next_actions = summary.get("next_actions") or []
    focus_score = float(summary.get("focus_score") or 0.0)

    # Characteristics of historical bad data: only abstract, overwritten by assistant original text slice, and still retains initialization placeholder value.
    if (
        abstract
        and not confirmed_facts
        and not open_questions
        and not next_actions
        and focus_score <= 0
        and (
            "##" in abstract
            or "|" in abstract
            or "---" in abstract
            or "**" in abstract
            or len(abstract) > 100
        )
    ):
        return None

    return {
        "abstract": abstract,
        "confirmed_facts": confirmed_facts,
        "open_questions": open_questions,
        "next_actions": next_actions,
        "focus_score": focus_score,
    }


def _thread_doc_to_item(doc: Dict[str, Any]) -> Dict[str, Any]:
    summary = _sanitize_thread_summary(doc.get("current_summary") or {})
    updated_at = doc.get("updated_at")
    if isinstance(updated_at, datetime):
        updated_at = updated_at.isoformat()
    report_refs = []
    for ref in doc.get("report_refs") or []:
        created_at = ref.get("created_at")
        linked_at = ref.get("linked_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        if isinstance(linked_at, datetime):
            linked_at = linked_at.isoformat()
        report_refs.append({
            "ref_type": ref.get("ref_type") or "unknown",
            "report_key": ref.get("report_key") or "",
            "source_collection": ref.get("source_collection") or "",
            "title": ref.get("title") or "未命名报告",
            "symbol": ref.get("symbol") or None,
            "summary": ref.get("summary") or "",
            "status": ref.get("status") or None,
            "task_id": ref.get("task_id") or None,
            "analysis_id": ref.get("analysis_id") or None,
            "created_at": created_at,
            "linked_at": linked_at,
        })
    return {
        "thread_id": doc.get("thread_id", ASSISTANT_DEFAULT_THREAD_ID),
        "title": doc.get("title") or "默认主题",
        "parent_thread_id": doc.get("parent_thread_id"),
        "topic_type": doc.get("topic_type") or "general",
        "pinned": bool(doc.get("pinned", False)),
        "archived": bool(doc.get("archived", False)),
        "message_count": int(doc.get("message_count", 0)),
        "last_user_message": doc.get("last_user_message", ""),
        "updated_at": updated_at,
        "report_refs": report_refs,
        "current_summary": {
            "abstract": summary.get("abstract") or "",
            "confirmed_facts": summary.get("confirmed_facts") or [],
            "open_questions": summary.get("open_questions") or [],
            "next_actions": summary.get("next_actions") or [],
            "focus_score": float(summary.get("focus_score") or 0.0),
        } if summary else None,
    }


def serialize_assistant_report_ref(ref: Dict[str, Any]) -> Dict[str, Any]:
    created_at = ref.get("created_at")
    linked_at = ref.get("linked_at")
    return {
        "ref_type": ref.get("ref_type") or "unknown",
        "report_key": ref.get("report_key") or "",
        "source_collection": ref.get("source_collection") or "",
        "title": ref.get("title") or "未命名报告",
        "symbol": ref.get("symbol") or None,
        "summary": ref.get("summary") or "",
        "status": ref.get("status") or None,
        "task_id": ref.get("task_id") or None,
        "analysis_id": ref.get("analysis_id") or None,
        "created_at": _to_iso_datetime(created_at),
        "linked_at": _to_iso_datetime(linked_at),
    }


def _normalize_summary_items(items: List[str], limit: int = 3) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for item in items:
        text = (item or "").strip().replace("\n", " ")
        if not text:
            continue
        text = text[:120]
        if text in seen:
            continue
        seen.add(text)
        normalized.append(text)
        if len(normalized) >= limit:
            break
    return normalized


def _normalize_report_ref_item(report_ref: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    ref_type = (report_ref.get("ref_type") or "").strip()
    report_key = (report_ref.get("report_key") or report_ref.get("task_id") or report_ref.get("analysis_id") or "").strip()
    if not ref_type or not report_key:
        return None

    now = _now_utc()
    created_at = report_ref.get("created_at")
    if not isinstance(created_at, datetime):
        created_at = now

    return {
        "ref_type": ref_type,
        "report_key": report_key,
        "source_collection": (report_ref.get("source_collection") or "").strip(),
        "title": (report_ref.get("title") or "未命名报告").strip(),
        "symbol": (report_ref.get("symbol") or "").strip() or None,
        "summary": (report_ref.get("summary") or "").strip()[:600],
        "status": (report_ref.get("status") or "").strip() or None,
        "task_id": (report_ref.get("task_id") or "").strip() or None,
        "analysis_id": (report_ref.get("analysis_id") or "").strip() or None,
        "created_at": created_at,
        "linked_at": now,
    }


async def attach_report_ref_to_thread(
    db,
    user_id: str,
    thread_id: Optional[str],
    report_ref: Dict[str, Any],
) -> bool:
    normalized_thread_id = (thread_id or "").strip()
    if not normalized_thread_id or _is_external_session_thread_id(normalized_thread_id):
        return False

    normalized_ref = _normalize_report_ref_item(report_ref)
    if not normalized_ref:
        return False

    thread = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": normalized_thread_id,
        "archived": {"$ne": True},
    })
    if not thread or (thread.get("topic_type") or "") == "im_session":
        return False

    existing_refs = thread.get("report_refs") or []
    merged_refs = [
        ref for ref in existing_refs
        if not (
            (ref.get("ref_type") or "") == normalized_ref["ref_type"]
            and (ref.get("report_key") or "") == normalized_ref["report_key"]
        )
    ]
    merged_refs.insert(0, normalized_ref)
    merged_refs = merged_refs[:ASSISTANT_MAX_REPORT_REFS]

    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": normalized_thread_id},
        {
            "$set": {
                "report_refs": merged_refs,
                "updated_at": _now_utc(),
            }
        },
    )
    return True


async def resolve_thread_for_report_writeback(
    db,
    user_id: str,
    preferred_thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_thread_id = (preferred_thread_id or "").strip()
    if normalized_thread_id and not _is_external_session_thread_id(normalized_thread_id):
        thread = await db.assistant_threads.find_one({
            "user_id": user_id,
            "thread_id": normalized_thread_id,
            "archived": {"$ne": True},
        })
        if thread and (thread.get("topic_type") or "") != "im_session":
            return thread

    fallback_thread = await create_assistant_thread(
        db,
        user_id=user_id,
        title=ASSISTANT_REPORT_INBOX_TITLE,
        parent_thread_id=None,
    )
    thread = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": fallback_thread["thread_id"],
        "archived": {"$ne": True},
    })
    return thread or fallback_thread


async def write_report_back_to_assistant_thread(
    db,
    user_id: str,
    report_ref: Dict[str, Any],
    preferred_thread_id: Optional[str] = None,
    summary_message: Optional[str] = None,
) -> Optional[str]:
    target_thread = await resolve_thread_for_report_writeback(db, user_id, preferred_thread_id)
    if not target_thread:
        return None

    target_thread_id = target_thread.get("thread_id")
    attached = await attach_report_ref_to_thread(db, user_id, target_thread_id, report_ref)
    if not attached:
        return None

    text = (summary_message or "").strip()
    if text:
        await append_assistant_message(
            db,
            user_id=user_id,
            role="assistant",
            content=text,
            conversation_id=target_thread_id,
            tools_used=["report_writeback"],
        )
        await summarize_assistant_thread(
            db,
            user_id=user_id,
            conversation_id=target_thread_id,
            summary_type="report_writeback",
        )

    return target_thread_id


def _to_iso_datetime(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    text = str(value or "").strip()
    return text or None


def _build_stock_report_detail_content(task: Any) -> str:
    result = task.result or {}
    symbol = task.task_params.get("symbol", "未知") if task.task_params else "未知"
    lines = [f"# {symbol} 分析报告"]

    recommendation = result.get("recommendation")
    if recommendation:
        lines.append(f"\n## 投资建议\n{recommendation}")

    summary = result.get("summary") or result.get("executive_summary")
    if summary:
        lines.append(f"\n## 摘要\n{summary}")

    decision = result.get("decision") or {}
    if decision:
        decision_lines: List[str] = []
        if decision.get("action"):
            decision_lines.append(f"- 操作观点: {decision['action']}")
        if decision.get("confidence") is not None:
            decision_lines.append(f"- 置信度: {decision['confidence']}")
        if decision.get("risk_score") is not None:
            decision_lines.append(f"- 风险分: {decision['risk_score']}")
        reasoning = decision.get("reasoning")
        if reasoning:
            decision_lines.append(f"- 决策依据: {reasoning}")
        if decision_lines:
            lines.append("\n## 决策信息\n" + "\n".join(decision_lines))

    key_points = result.get("key_points") or []
    if key_points:
        lines.append("\n## 关键要点\n" + "\n".join(f"- {item}" for item in key_points[:8]))

    reports = result.get("reports") or {}
    if reports:
        lines.append("\n## 分析师摘录")
        for key, text in reports.items():
            cleaned = str(text or "").strip()
            if not cleaned:
                continue
            lines.append(f"\n### {key}\n{cleaned[:1500]}")

    lines.append(f"\n---\n Task ID: {task.task_id}")
    return "\n".join(lines)


def _build_stock_report_detail_content_from_doc(report_doc: Dict[str, Any]) -> str:
    stock_symbol = (report_doc.get("stock_symbol") or "未知").strip() or "未知"
    stock_name = (report_doc.get("stock_name") or "").strip()
    title = f"{stock_name}({stock_symbol})" if stock_name else stock_symbol
    lines = [f"# {title} 分析报告"]

    recommendation = str(report_doc.get("recommendation") or "").strip()
    if recommendation:
        lines.append(f"\n## 投资建议\n{recommendation}")

    summary = str(report_doc.get("summary") or "").strip()
    if summary:
        lines.append(f"\n## 摘要\n{summary}")

    decision = report_doc.get("decision") or {}
    if isinstance(decision, dict) and decision:
        decision_lines: List[str] = []
        if decision.get("action"):
            decision_lines.append(f"- 操作观点: {decision['action']}")
        if decision.get("confidence") is not None:
            decision_lines.append(f"- 置信度: {decision['confidence']}")
        if decision.get("risk_score") is not None:
            decision_lines.append(f"- 风险分: {decision['risk_score']}")
        reasoning = decision.get("reasoning")
        if reasoning:
            decision_lines.append(f"- 决策依据: {reasoning}")
        if decision_lines:
            lines.append("\n## 决策信息\n" + "\n".join(decision_lines))

    key_points = report_doc.get("key_points") or []
    if key_points:
        lines.append("\n## 关键要点\n" + "\n".join(f"- {item}" for item in key_points[:8]))

    reports = report_doc.get("reports") or {}
    if isinstance(reports, dict) and reports:
        lines.append("\n## 分析师摘录")
        for key, text in reports.items():
            cleaned = str(text or "").strip()
            if not cleaned:
                continue
            lines.append(f"\n### {key}\n{cleaned[:1500]}")

    if report_doc.get("analysis_id"):
        lines.append(f"\n---\n analysis ID: {report_doc['analysis_id']}")
    if report_doc.get("task_id"):
        lines.append(f"任务ID: {report_doc['task_id']}")
    return "\n".join(lines)


def _build_position_report_detail_content(report: Dict[str, Any]) -> str:
    code = report.get("code") or "未知"
    name = report.get("name") or code
    lines = [f"# {name}({code}) 持仓分析报告"]

    status = report.get("status")
    action = report.get("action")
    confidence = report.get("confidence")
    meta: List[str] = []
    if status:
        meta.append(f"- 状态: {status}")
    if action:
        meta.append(f"- 研究观察: {action}")
    if confidence is not None:
        meta.append(f"- 置信度: {confidence}")
    if meta:
        lines.append("\n## 核心结论\n" + "\n".join(meta))

    summary = report.get("summary") or {}
    summary_lines: List[str] = []
    if summary.get("quantity") is not None:
        summary_lines.append(f"- 持仓数量: {summary['quantity']}")
    if summary.get("cost_price") is not None:
        summary_lines.append(f"- 成本价: {summary['cost_price']}")
    if summary.get("current_price") is not None:
        summary_lines.append(f"- 当前价: {summary['current_price']}")
    if summary.get("unrealized_pnl") is not None:
        summary_lines.append(f"- 浮动盈亏: {summary['unrealized_pnl']}")
    if summary.get("unrealized_pnl_pct") is not None:
        summary_lines.append(f"- 盈亏比例: {summary['unrealized_pnl_pct']}%")
    if summary_lines:
        lines.append("\n## 持仓概览\n" + "\n".join(summary_lines))

    targets = report.get("price_targets") or {}
    target_lines: List[str] = []
    for label, key in (("关键验证价位", "target_price"), ("风险关注价格", "stop_loss"), ("收益关注价格", "take_profit_price")):
        if targets.get(key) is not None:
            target_lines.append(f"- {label}: {targets[key]}")
    if target_lines:
        lines.append("\n## 关键价位\n" + "\n".join(target_lines))

    action_reason = str(report.get("action_reason") or "").strip()
    if action_reason:
        lines.append(f"\n## 分析详情\n{action_reason}")

    detailed = str(report.get("detailed_analysis") or "").strip()
    if detailed:
        lines.append(f"\n## 详细分析\n{detailed}")

    analysis_id = report.get("analysis_id")
    if analysis_id:
        lines.append(f"\n---\n analysis ID: {analysis_id}")
    return "\n".join(lines)


def _build_review_report_detail_content(review_data: Dict[str, Any]) -> str:
    """Construct transaction review report data into Markdown detailed content."""
    trade_info = review_data.get("trade_info") or {}
    code = trade_info.get("code") or "未知"
    name = trade_info.get("name") or code
    lines = [f"# {name}({code}) 交易复盘报告"]

    status = review_data.get("status")
    execution_time = review_data.get("execution_time")
    meta: List[str] = []
    if status:
        meta.append(f"- 状态: {status}")
    if execution_time is not None:
        meta.append(f"- 执行耗时: {execution_time:.1f}s")
    source = review_data.get("source")
    if source:
        meta.append(f"- 来源: {'实盘' if source == 'position' else '模拟'}")
    if meta:
        lines.append("\n## 核心信息\n" + "\n".join(meta))

    # Transaction Overview
    summary_lines: List[str] = []
    if trade_info.get("code"):
        summary_lines.append(f"- 股票代码: {trade_info['code']}")
    if trade_info.get("name"):
        summary_lines.append(f"- 股票名称: {trade_info['name']}")
    if trade_info.get("realized_pnl") is not None:
        summary_lines.append(f"- 实现盈亏: {trade_info['realized_pnl']}")
    if trade_info.get("remaining_quantity") is not None:
        summary_lines.append(f"- 剩余持仓: {trade_info['remaining_quantity']} 股")
    if summary_lines:
        lines.append("\n## 交易概览\n" + "\n".join(summary_lines))

    # AI Review content
    ai_review = review_data.get("ai_review") or {}
    if ai_review.get("summary"):
        lines.append(f"\n## 复盘结论\n{ai_review['summary']}")
    if ai_review.get("strengths"):
        lines.append("\n## 做得好的地方\n" + "\n".join(f"- {s}" for s in ai_review["strengths"]))
    if ai_review.get("weaknesses"):
        lines.append("\n## 需要改进的地方\n" + "\n".join(f"- {w}" for w in ai_review["weaknesses"]))
    if ai_review.get("suggestions"):
        lines.append("\n## 后续观察点\n" + "\n".join(f"- {s}" for s in ai_review["suggestions"]))
    if ai_review.get("plan_deviation"):
        lines.append(f"\n## 计划偏离\n{ai_review['plan_deviation']}")

    review_id = review_data.get("review_id")
    if review_id:
        lines.append(f"\n---\n Review ID: {review_id}")
    return "\n".join(lines)


async def get_assistant_thread_report_detail(
    db,
    user_id: str,
    thread_id: str,
    ref_type: str,
    report_key: str,
) -> Dict[str, Any]:
    thread = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not thread:
        raise ValueError("主题不存在或已删除")

    target_ref = None
    for ref in thread.get("report_refs") or []:
        if (ref.get("ref_type") or "") == ref_type and (ref.get("report_key") or "") == report_key:
            target_ref = ref
            break
    if not target_ref:
        raise ValueError("No corresponding related report was found under the current topic.")

    detail = {
        "ref_type": target_ref.get("ref_type") or ref_type,
        "report_key": target_ref.get("report_key") or report_key,
        "title": target_ref.get("title") or "未命名报告",
        "symbol": target_ref.get("symbol") or None,
        "status": target_ref.get("status") or None,
        "task_id": target_ref.get("task_id") or None,
        "analysis_id": target_ref.get("analysis_id") or None,
        "created_at": _to_iso_datetime(target_ref.get("created_at")),
        "linked_at": _to_iso_datetime(target_ref.get("linked_at")),
        "content": (target_ref.get("summary") or "").strip(),
        "content_format": "markdown",
    }

    if ref_type == "stock_report":
        from app.services.task_analysis_service import get_task_analysis_service

        task_id = (target_ref.get("task_id") or report_key or "").strip()
        task = await get_task_analysis_service().get_task(task_id) if task_id else None
        if task and str(task.user_id) == str(user_id):
            detail["status"] = str(task.status)
            detail["created_at"] = _to_iso_datetime(task.created_at)
            detail["content"] = _build_stock_report_detail_content(task)
            return detail

        analysis_key = (target_ref.get("analysis_id") or report_key or task_id or "").strip()
        report_doc = await db.analysis_reports.find_one(_build_analysis_report_lookup_query(user_id, analysis_key))
        if not report_doc:
            raise ValueError("原始报告不存在或已被删除")
        detail["status"] = report_doc.get("status") or detail["status"]
        detail["task_id"] = report_doc.get("task_id") or detail["task_id"]
        detail["analysis_id"] = report_doc.get("analysis_id") or detail["analysis_id"]
        detail["created_at"] = _to_iso_datetime(report_doc.get("created_at"))
        detail["content"] = _build_stock_report_detail_content_from_doc(report_doc)
        return detail

    if ref_type == "position_report":
        from app.services.portfolio_service import get_portfolio_service

        analysis_id = (target_ref.get("analysis_id") or report_key or "").strip()
        report = await get_portfolio_service().get_position_analysis_by_id(user_id, analysis_id)
        if not report:
            raise ValueError("The original position report does not exist or has been deleted")
        detail["created_at"] = _to_iso_datetime(report.get("created_at"))
        detail["content"] = _build_position_report_detail_content(report)
        detail["status"] = report.get("status") or detail["status"]
        return detail

    if ref_type == "review_report":
        from app.services.trade_review_service import TradeReviewService

        review_id = (target_ref.get("task_id") or report_key or "").strip()
        service = TradeReviewService()
        review = await service.get_review_detail(user_id, review_id)
        if not review:
            raise ValueError("The original transaction review report does not exist or has been deleted")
        review_data = review.model_dump() if hasattr(review, "model_dump") else dict(review)
        detail["created_at"] = _to_iso_datetime(review_data.get("created_at"))
        detail["status"] = review_data.get("status") or detail["status"]
        detail["content"] = _build_review_report_detail_content(review_data)
        return detail

    if ref_type == "position_task":
        task_id = (target_ref.get("task_id") or report_key or "").strip()
        task_doc = await db.unified_analysis_tasks.find_one({"task_id": task_id})
        if not task_doc:
            raise ValueError("原始任务不存在或已被删除")
        if str(task_doc.get("user_id")) != str(user_id):
            raise ValueError("无权访问该任务")

        result = task_doc.get("result") or {}
        analysis_id = (result.get("analysis_id") or target_ref.get("analysis_id") or "").strip()
        if analysis_id:
            from app.services.portfolio_service import get_portfolio_service

            report = await get_portfolio_service().get_position_analysis_by_id(user_id, analysis_id)
            if report:
                detail["analysis_id"] = analysis_id
                detail["created_at"] = _to_iso_datetime(report.get("created_at"))
                detail["status"] = report.get("status") or detail["status"]
                detail["content"] = _build_position_report_detail_content(report)
                return detail

        status = task_doc.get("status") or detail["status"] or "unknown"
        detail["status"] = str(status)
        detail["created_at"] = _to_iso_datetime(task_doc.get("created_at"))
        detail["content"] = (
            f"# {detail['title']}\n\n"
            f"- Task status: {status}\n"
            f"- Task ID: {task_id}\n\n"
            f"{(target_ref.get('summary') or 'This task has not yet generated a complete report, which can be viewed here after completion.').strip()}"
        )
        return detail

    return detail


def _build_stock_report_ref_from_task(task: Any, stock_name: Optional[str] = None) -> Dict[str, Any]:
    result = task.result or {}
    task_params = task.task_params or {}
    symbol = (task_params.get("symbol") or "").strip()
    display_name = (stock_name or "").strip()
    title_prefix = f"{display_name}({symbol})" if display_name and symbol else display_name or symbol or "未知标的"
    return {
        "ref_type": "stock_report",
        "report_key": task.task_id,
        "source_collection": "unified_analysis_tasks",
        "title": f"{title_prefix} 分析报告",
        "symbol": symbol or None,
        "summary": ((result.get("summary") or result.get("recommendation") or "")[:400]).strip(),
        "status": str(task.status),
        "task_id": task.task_id,
        "created_at": getattr(task, "created_at", None),
    }


def _build_stock_report_ref_from_analysis_doc(report_doc: Dict[str, Any]) -> Dict[str, Any]:
    stock_symbol = (report_doc.get("stock_symbol") or "").strip()
    stock_name = (report_doc.get("stock_name") or "").strip()
    title_prefix = f"{stock_name}({stock_symbol})" if stock_name and stock_symbol else stock_name or stock_symbol or "未知标的"
    report_key = (report_doc.get("task_id") or report_doc.get("analysis_id") or str(report_doc.get("_id") or "")).strip()
    return {
        "ref_type": "stock_report",
        "report_key": report_key,
        "source_collection": "analysis_reports",
        "title": f"{title_prefix} 分析报告",
        "symbol": stock_symbol or None,
        "summary": ((report_doc.get("summary") or report_doc.get("recommendation") or "")[:400]).strip(),
        "status": report_doc.get("status") or "completed",
        "task_id": (report_doc.get("task_id") or "").strip() or None,
        "analysis_id": (report_doc.get("analysis_id") or "").strip() or None,
        "created_at": report_doc.get("created_at"),
    }


def _build_analysis_report_lookup_query(user_id: str, report_key: str) -> Dict[str, Any]:
    report_query = {
        "$or": [
            {"task_id": report_key},
            {"analysis_id": report_key},
        ]
    }
    if ObjectId.is_valid(report_key):
        report_query["$or"].append({"_id": ObjectId(report_key)})

    return {
        "$and": [
            {"$or": [{"user_id": user_id}, {"user_id": str(user_id)}]},
            report_query,
        ]
    }


def _build_position_report_ref_from_report(report: Dict[str, Any]) -> Dict[str, Any]:
    code = (report.get("code") or "").strip()
    name = (report.get("name") or "").strip()
    title_prefix = f"{name}({code})" if name and code else name or code or "未知持仓"
    return {
        "ref_type": "position_report",
        "report_key": report.get("analysis_id") or "",
        "source_collection": "position_analysis_reports",
        "title": f"{title_prefix} 持仓分析",
        "symbol": code or None,
        "summary": ((report.get("summary") or report.get("action_reason") or "")[:400]).strip(),
        "status": report.get("status") or None,
        "analysis_id": report.get("analysis_id") or None,
        "created_at": report.get("created_at"),
    }


def _build_review_report_ref_from_review(review: Any) -> Dict[str, Any]:
    """Construct topic association references from transaction review report objects.

    Compatible with TradeReviewReport objects(Pydantic) and dictionary forms.
    """
    if hasattr(review, "model_dump"):
        data = review.model_dump()
    elif hasattr(review, "dict"):
        data = review.dict()
    else:
        data = dict(review)

    trade_info = data.get("trade_info") or {}
    code = (trade_info.get("code") or "").strip()
    name = (trade_info.get("name") or "").strip()
    title_prefix = f"{name}({code})" if name and code else name or code or "未知标的"

    ai_review = data.get("ai_review") or {}
    summary_text = (ai_review.get("summary") or "").strip()

    return {
        "ref_type": "review_report",
        "report_key": data.get("review_id") or data.get("task_id") or "",
        "source_collection": "trade_reviews",
        "title": f"{title_prefix} 交易复盘",
        "symbol": code or None,
        "summary": summary_text[:600],
        "status": data.get("status") or "completed",
        "task_id": data.get("review_id") or data.get("task_id") or None,
        "created_at": data.get("created_at"),
    }


async def search_assistant_attachable_reports(
    db,
    user_id: str,
    thread_id: str,
    ref_type: str = "stock_report",
    keyword: Optional[str] = None,
    limit: int = 8,
) -> List[Dict[str, Any]]:
    thread = await db.assistant_threads.find_one({
        "user_id": user_id,
        "thread_id": thread_id,
        "archived": {"$ne": True},
    })
    if not thread or (thread.get("topic_type") or "") == "im_session":
        raise ValueError("The current topic does not exist or does not support associated reports")

    normalized_type = (ref_type or "stock_report").strip() or "stock_report"
    normalized_keyword = (keyword or "").strip()
    limit = max(1, min(limit, 20))

    if normalized_type == "position_report":
        from app.services.portfolio_service import get_portfolio_service

        query: Dict[str, Any] = {
            "user_id": user_id,
            "analysis_id": {"$exists": True, "$ne": ""},
        }
        if normalized_keyword:
            query["$or"] = [
                {"code": {"$regex": normalized_keyword, "$options": "i"}},
                {"name": {"$regex": normalized_keyword, "$options": "i"}},
                {"summary": {"$regex": normalized_keyword, "$options": "i"}},
                {"analysis_id": {"$regex": normalized_keyword, "$options": "i"}},
            ]

        docs = await db.position_analysis_reports.find(query).sort("created_at", -1).limit(limit).to_list(length=limit)
        service = get_portfolio_service()
        results: List[Dict[str, Any]] = []
        for doc in docs:
            analysis_id = (doc.get("analysis_id") or "").strip()
            if not analysis_id:
                continue
            report = await service.get_position_analysis_by_id(user_id, analysis_id)
            if not report:
                continue
            results.append(_normalize_report_ref_item(_build_position_report_ref_from_report(report)))
        return [item for item in results if item][:limit]

    if normalized_type == "review_report":
        # Trade review report candidates: query from the trade_reviews collection
        review_query: Dict[str, Any] = {
            "user_id": user_id,
        }
        if normalized_keyword:
            review_query["$or"] = [
                {"trade_info.code": {"$regex": normalized_keyword, "$options": "i"}},
                {"trade_info.name": {"$regex": normalized_keyword, "$options": "i"}},
                {"review_id": {"$regex": normalized_keyword, "$options": "i"}},
                {"ai_review.summary": {"$regex": normalized_keyword, "$options": "i"}},
            ]

        review_docs = await db["trade_reviews"].find(review_query).sort("created_at", -1).limit(limit).to_list(length=limit)
        review_results: List[Dict[str, Any]] = []
        from app.services.trade_review_service import TradeReviewService

        review_service = TradeReviewService()
        for doc in review_docs:
            review_id = (doc.get("review_id") or "").strip()
            if not review_id:
                continue
            review = await review_service.get_review_detail(user_id, review_id)
            if not review:
                continue
            ref = _normalize_report_ref_item(_build_review_report_ref_from_review(review))
            if ref:
                review_results.append(ref)
            if len(review_results) >= limit:
                break
        return review_results[:limit]

    from app.services.task_analysis_service import get_task_analysis_service

    service = get_task_analysis_service()
    results: List[Dict[str, Any]] = []
    seen_keys = set()

    if normalized_keyword:
        analysis_query: Dict[str, Any] = {
            "$and": [
                {"$or": [{"user_id": user_id}, {"user_id": str(user_id)}]},
                {
                    "$or": [
                        {"stock_symbol": {"$regex": normalized_keyword, "$options": "i"}},
                        {"stock_name": {"$regex": normalized_keyword, "$options": "i"}},
                        {"summary": {"$regex": normalized_keyword, "$options": "i"}},
                        {"analysis_id": {"$regex": normalized_keyword, "$options": "i"}},
                        {"task_id": {"$regex": normalized_keyword, "$options": "i"}},
                    ]
                },
            ]
        }
        analysis_docs = await db.analysis_reports.find(analysis_query).sort("created_at", -1).limit(limit * 3).to_list(length=limit * 3)
        for doc in analysis_docs:
            ref = _normalize_report_ref_item(_build_stock_report_ref_from_analysis_doc(doc))
            ref_key = (ref or {}).get("report_key") if ref else None
            if not ref_key or ref_key in seen_keys:
                continue
            if ref:
                results.append(ref)
                seen_keys.add(ref_key)
            if len(results) >= limit:
                return results[:limit]

    task_query: Dict[str, Any] = {
        "$and": [
            {"status": "completed"},
            {"$or": [{"user_id": user_id}, {"user_id": ObjectId(user_id)}]},
        ]
    }
    if normalized_keyword:
        task_query["$and"].append({
            "$or": [
                {"task_params.symbol": {"$regex": normalized_keyword, "$options": "i"}},
                {"result.summary": {"$regex": normalized_keyword, "$options": "i"}},
                {"result.recommendation": {"$regex": normalized_keyword, "$options": "i"}},
                {"task_id": {"$regex": normalized_keyword, "$options": "i"}},
            ]
        })

    task_docs = await db.unified_analysis_tasks.find(task_query).sort("created_at", -1).limit(limit * 2).to_list(length=limit * 2)
    for doc in task_docs:
        task_id = (doc.get("task_id") or "").strip()
        if not task_id or task_id in seen_keys:
            continue
        task = await service.get_task(task_id)
        if not task or str(task.user_id) != str(user_id) or str(task.status) != "completed":
            continue
        ref = _normalize_report_ref_item(_build_stock_report_ref_from_task(task))
        if ref:
            results.append(ref)
            seen_keys.add(task_id)
        if len(results) >= limit:
            break

    return results[:limit]


async def attach_existing_report_to_thread(
    db,
    user_id: str,
    thread_id: str,
    ref_type: str,
    report_key: str,
) -> Dict[str, Any]:
    normalized_type = (ref_type or "").strip()
    normalized_key = (report_key or "").strip()
    if not normalized_type or not normalized_key:
        raise ValueError("Report type and report ID cannot be empty")

    if normalized_type == "position_report":
        from app.services.portfolio_service import get_portfolio_service

        report = await get_portfolio_service().get_position_analysis_by_id(user_id, normalized_key)
        if not report:
            raise ValueError("未找到可关联的持仓报告")
        ref = _normalize_report_ref_item(_build_position_report_ref_from_report(report))
    elif normalized_type == "review_report":
        from app.services.trade_review_service import TradeReviewService

        service = TradeReviewService()
        review = await service.get_review_detail(user_id, normalized_key)
        if not review:
            raise ValueError("No relevant transaction review report found")
        ref = _normalize_report_ref_item(_build_review_report_ref_from_review(review))
    else:
        from app.services.task_analysis_service import get_task_analysis_service

        task = await get_task_analysis_service().get_task(normalized_key)
        if task and str(task.user_id) == str(user_id) and str(task.status) == "completed":
            ref = _normalize_report_ref_item(_build_stock_report_ref_from_task(task))
        else:
            report_doc = await db.analysis_reports.find_one(_build_analysis_report_lookup_query(user_id, normalized_key))
            if not report_doc:
                raise ValueError("No relevant historical analysis report found")
            ref = _normalize_report_ref_item(_build_stock_report_ref_from_analysis_doc(report_doc))

    if not ref:
        raise ValueError("Report information is incomplete and cannot be associated")

    attached = await attach_report_ref_to_thread(db, user_id, thread_id, ref)
    if not attached:
        raise ValueError("当前主题不支持关联该报告")
    return ref


def _extract_sentences(text: str) -> List[str]:
    raw = (text or "").replace("\r", "\n")
    fragments: List[str] = []
    for chunk in raw.split("\n"):
        chunk = chunk.strip(" -•\t")
        if not chunk:
            continue
        parts = [part.strip() for part in chunk.replace("！", "。").replace("？", "。").split("。")]
        for part in parts:
            if part:
                fragments.append(part)
    return fragments


def _format_messages_for_summary(messages: List[Dict[str, Any]], limit: int = 12) -> str:
    """Format recent messages for topic summary use.

    Double-layer budget: latest limit, 800 characters per message, total capped at 6,000 characters——
    The abstract only needs to grasp the focus of the topic and does not require the complete text; long input costs tokens and increases the cost.
    Timeout probability under slow endpoint. When the budget is exceeded, the most recent messages are retained first (accumulated from the tail).
    """
    _PER_MSG_BUDGET = 800
    _TOTAL_BUDGET = 6000
    recent = messages[-limit:]
    # Accumulate in reverse order (prioritize the latest news), and finally output in chronological order
    picked: List[str] = []
    used = 0
    for back_index, message in enumerate(reversed(recent), start=1):
        role = str(message.get("role") or "assistant").strip() or "assistant"
        content = str(message.get("content") or "").strip()
        if not content:
            continue
        content = re.sub(r"\s+", " ", content)
        index = len(recent) - back_index + 1
        line = f"{index}. [{role}] {content[:_PER_MSG_BUDGET]}"
        if used + len(line) > _TOTAL_BUDGET:
            # Older messages are no longer included
            break
        picked.append(line)
        used += len(line)
    return "\n".join(reversed(picked))


def _strip_json_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _load_summary_json(text: str) -> Dict[str, Any]:
    cleaned = _strip_json_code_fence(text)
    if not cleaned:
        raise ValueError("摘要模型返回为空")

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        data = json.loads(match.group(0))

    if not isinstance(data, dict):
        raise ValueError("The summary model returns something other than JSON object")
    return data


def _normalize_thread_summary_payload(payload: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    abstract = str(payload.get("abstract") or "").strip()
    focus_score = payload.get("focus_score")
    try:
        focus_score = float(focus_score)
    except (TypeError, ValueError):
        focus_score = fallback.get("focus_score") or 0.0
    focus_score = max(0.0, min(round(float(focus_score), 2), 1.0))

    return {
        "abstract": abstract[:160] or fallback.get("abstract") or "当前主题尚未形成摘要",
        "confirmed_facts": _normalize_summary_items(payload.get("confirmed_facts") or fallback.get("confirmed_facts") or []),
        "open_questions": _normalize_summary_items(payload.get("open_questions") or fallback.get("open_questions") or []),
        "next_actions": _normalize_summary_items(payload.get("next_actions") or fallback.get("next_actions") or []),
        "focus_score": focus_score,
    }


async def _build_thread_summary_with_llm(
    db,
    messages: List[Dict[str, Any]],
    title: str = "",
) -> Dict[str, Any]:
    fallback = _build_thread_summary_from_messages(messages, title)
    transcript = _format_messages_for_summary(messages)
    if not transcript:
        return fallback

    try:
        llm_config = await get_coding_llm_config(db)
        if not llm_config:
            logger.warning("[Smart Assistant Summary] No available LLM configuration found, fallback rule summary")
            return fallback

        summary_config = llm_config.model_copy(deep=True) if hasattr(llm_config, "model_copy") else llm_config.copy(deep=True)
        summary_config.temperature = 0.1
        summary_config.max_tokens = min(int(summary_config.max_tokens or 600), 600)
        # The summary is a background display task (summary of fallback rules if failure occurs), and timeouts and retries must be tightened:
        # Outputs only 600 tokens of JSON, and returns normally in a few seconds; if it does not return for 25 seconds, it is basically the endpoint is stuck.
        # Retry 3 times with exponential backoff (old configuration 45s×3 ≈ 2.5 minutes) without any benefit.
        summary_config.timeout = 25
        summary_config.retry_times = 0

        client = UnifiedLLMClient.from_config(summary_config)
        messages_for_llm = [
            Message(
                role=MessageRole.SYSTEM,
                content=(
                    "You are the research topic summarizer. Your task is to generate structured summaries of topic sessions for display in sidebars and topic cards.\n"
                    "You must only output a JSON object, do not output markdown, code blocks, explanations, and suffixes.\n"
                    "Field requirements:\n"
                    "- abstract: 1-2 A Chinese summary of 40-90 words, highlighting the current conclusion or discussion focus. Do not copy large sections of the original text, and do not retain markdown titles, tables, and separators.\n"
                    "- confirmed_facts: 1-3 The facts that have been clearly stated in the conversation must be specific and not empty words.\n"
                    "- open_questions: 0-3 Questions that remain to be answered; if the question has already been answered, do not include it again.\n"
                    "- next_actions: 1-3 Suggestions for next steps must fit the current topic.\n"
                    "- focus_score: 0 A decimal number between 1 and 1 indicating whether the current topic is focused.\n"
                    "If there is insufficient information, err on the side of brevity rather than copying fragments of the text."
                ),
            ),
            Message(
                role=MessageRole.USER,
                content=(
                    f"主题标题: {title or '未命名主题'}\n"
                    "The latest news is as follows:\n"
                    f"{transcript}\n\n"
                    "Please output JSON:\n"
                    "{\n"
                    '  "abstract": "",\n'
                    '  "confirmed_facts": [],\n'
                    '  "open_questions": [],\n'
                    '  "next_actions": [],\n'
                    '  "focus_score": 0.0\n'
                    "}"
                ),
            ),
        ]

        response = await client.achat(messages_for_llm)
        await _record_assistant_token_usage(response, "assistant_summary", analysis_type="assistant_summary")
        payload = _load_summary_json(response.content or "")
        summary = _normalize_thread_summary_payload(payload, fallback)
        logger.info("[Smart Assistant Summary] Using LLM to generate structured snippets successfully")
        return summary
    except Exception as exc:
        logger.warning("[Smart Assistant Summary] LLM Summary generation failed, fallback rule summary: %s", exc)
        return fallback


def _build_thread_summary_from_messages(messages: List[Dict[str, Any]], title: str = "") -> Dict[str, Any]:
    user_messages = [m.get("content", "").strip() for m in messages if m.get("role") == "user" and m.get("content")]
    assistant_messages = [m.get("content", "").strip() for m in messages if m.get("role") == "assistant" and m.get("content")]

    latest_user = user_messages[-1] if user_messages else ""
    latest_assistant = assistant_messages[-1] if assistant_messages else ""
    abstract = latest_assistant[:160] or latest_user[:160] or (title[:160] if title else "") or "当前主题尚未形成摘要"

    confirmed_candidates: List[str] = []
    for content in reversed(assistant_messages[-4:]):
        confirmed_candidates.extend(_extract_sentences(content))

    question_candidates: List[str] = []
    for content in reversed(user_messages[-4:]):
        question_candidates.extend(_extract_sentences(content))

    next_actions: List[str] = []
    if latest_user:
        next_actions.append(f"围绕“{latest_user[:40]}”继续追问或补数")
    if latest_assistant:
        next_actions.append("Continue to refine valuation, industry or risk main lines based on current conclusions.")
    if not next_actions:
        next_actions.append("Continue to add questions under the current topic or trigger in-depth analysis")

    total_messages = len(messages)
    assistant_ratio = len(assistant_messages) / total_messages if total_messages else 0
    focus_score = 0.55
    if total_messages >= 4:
        focus_score += 0.1
    if total_messages >= 8:
        focus_score += 0.05
    if latest_user and title and any(token for token in title.split() if token and token in latest_user):
        focus_score += 0.1
    if assistant_ratio >= 0.4:
        focus_score += 0.1
    focus_score = min(round(focus_score, 2), 0.95)

    return {
        "abstract": abstract,
        "confirmed_facts": _normalize_summary_items(confirmed_candidates),
        "open_questions": _normalize_summary_items(question_candidates),
        "next_actions": _normalize_summary_items(next_actions),
        "focus_score": focus_score,
    }


async def _create_thread_document(
    db,
    user_id: str,
    thread_id: str,
    title: str,
    parent_thread_id: Optional[str] = None,
    topic_type: str = "general",
) -> Dict[str, Any]:
    now = _now_utc()
    doc = {
        "thread_id": thread_id,
        "user_id": user_id,
        "title": title,
        "parent_thread_id": parent_thread_id,
        "topic_type": topic_type,
        "pinned": thread_id == ASSISTANT_DEFAULT_THREAD_ID,
        "archived": False,
        "message_count": 0,
        "last_user_message": "",
        "report_refs": [],
        "current_summary": {
            "abstract": "",
            "confirmed_facts": [],
            "open_questions": [],
            "next_actions": [],
            "focus_score": 0.0,
        },
        "created_at": now,
        "updated_at": now,
    }
    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": thread_id},
        {"$setOnInsert": doc},
        upsert=True,
    )
    return await db.assistant_threads.find_one({"user_id": user_id, "thread_id": thread_id})


async def _migrate_legacy_conversation_if_needed(db, user_id: str, thread_id: str) -> None:
    if thread_id != ASSISTANT_DEFAULT_THREAD_ID:
        return

    message_count = await db.assistant_thread_messages.count_documents({
        "user_id": user_id,
        "thread_id": thread_id,
    })
    if message_count > 0:
        return

    legacy_doc = await db.assistant_conversations.find_one({"user_id": user_id})
    legacy_messages = (legacy_doc or {}).get("messages") or []
    if not legacy_messages:
        return

    now = _now_utc()
    payload = []
    last_user_message = ""
    for idx, message in enumerate(legacy_messages):
        content = (message.get("content") or "").strip()
        if not content:
            continue
        role = message.get("role") or "assistant"
        if role == "user":
            last_user_message = content
        payload.append({
            "message_id": f"legacy_{idx}_{uuid.uuid4().hex[:8]}",
            "thread_id": thread_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "tools_used": message.get("tools_used") or [],
            "created_at": now,
        })

    if not payload:
        return

    await db.assistant_thread_messages.insert_many(payload)
    abstract = ""
    for message in reversed(payload):
        if message["role"] == "assistant":
            abstract = message["content"][:120]
            break

    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": thread_id},
        {
            "$set": {
                "message_count": len(payload),
                "last_user_message": last_user_message,
                "current_summary": {
                    "abstract": abstract,
                    "confirmed_facts": [],
                    "open_questions": [],
                    "next_actions": [],
                    "focus_score": 0.5,
                },
                "updated_at": now,
            }
        },
    )


async def get_or_create_assistant_thread(
    db,
    user_id: str,
    conversation_id: Optional[str] = None,
) -> Dict[str, Any]:
    thread_id = (conversation_id or ASSISTANT_DEFAULT_THREAD_ID).strip() if conversation_id else ASSISTANT_DEFAULT_THREAD_ID
    topic_type = "im_session" if _is_external_session_thread_id(thread_id) else "general"
    doc = await db.assistant_threads.find_one({"user_id": user_id, "thread_id": thread_id})
    if doc is None:
        title = "默认主题" if thread_id == ASSISTANT_DEFAULT_THREAD_ID else ("外部会话" if topic_type == "im_session" else f"新主题 {datetime.now().strftime('%m-%d %H:%M')}")
        doc = await _create_thread_document(db, user_id, thread_id, title, topic_type=topic_type)
    elif topic_type == "im_session" and doc.get("topic_type") != "im_session":
        await db.assistant_threads.update_one(
            {"user_id": user_id, "thread_id": thread_id},
            {
                "$set": {
                    "topic_type": "im_session",
                    "title": doc.get("title") or "外部会话",
                    "updated_at": _now_utc(),
                }
            },
        )
    await _migrate_legacy_conversation_if_needed(db, user_id, thread_id)
    return await db.assistant_threads.find_one({"user_id": user_id, "thread_id": thread_id})


async def list_assistant_threads(db, user_id: str) -> List[Dict[str, Any]]:
    await get_or_create_assistant_thread(db, user_id)
    items: List[Dict[str, Any]] = []
    cursor = db.assistant_threads.find({
        "user_id": user_id,
        "archived": {"$ne": True},
    }).sort([("pinned", -1), ("parent_thread_id", 1), ("updated_at", -1)])
    async for doc in cursor:
        if _is_visible_assistant_topic(doc):
            items.append(_thread_doc_to_item(doc))
    return items


async def create_assistant_thread(
    db,
    user_id: str,
    title: Optional[str] = None,
    parent_thread_id: Optional[str] = None,
) -> Dict[str, Any]:
    normalized_parent_id = (parent_thread_id or "").strip() or None
    if normalized_parent_id:
        parent = await db.assistant_threads.find_one({
            "user_id": user_id,
            "thread_id": normalized_parent_id,
            "archived": {"$ne": True},
        })
        if not parent:
            raise ValueError("父主题不存在或已删除")

    thread_id = _generate_thread_id()
    thread_title = (title or "").strip() or f"新主题 {datetime.now().strftime('%m-%d %H:%M')}"
    existing_docs = await db.assistant_threads.find({
        "user_id": user_id,
        "archived": {"$ne": True},
    }).to_list(length=None)
    existing_docs = [doc for doc in existing_docs if _is_visible_assistant_topic(doc)]
    similar_doc = _find_similar_thread(existing_docs, thread_title, normalized_parent_id)
    if similar_doc:
        return _thread_doc_to_item(similar_doc)

    doc = await _create_thread_document(
        db,
        user_id,
        thread_id,
        thread_title,
        parent_thread_id=normalized_parent_id,
        topic_type="subtopic" if normalized_parent_id else "general",
    )
    return _thread_doc_to_item(doc)


async def delete_assistant_thread(db, user_id: str, thread_id: str) -> List[str]:
    normalized_thread_id = (thread_id or "").strip()
    if not normalized_thread_id:
        raise ValueError("主题 ID 不能为空")
    if normalized_thread_id == ASSISTANT_DEFAULT_THREAD_ID:
        raise ValueError("默认主题不能删除")

    docs = await db.assistant_threads.find({
        "user_id": user_id,
        "archived": {"$ne": True},
    }).to_list(length=None)
    docs = [doc for doc in docs if _is_visible_assistant_topic(doc)]

    by_id = {doc.get("thread_id"): doc for doc in docs}
    if normalized_thread_id not in by_id:
        raise ValueError("主题不存在或已删除")

    children_by_parent: Dict[str, List[str]] = {}
    for doc in docs:
        parent_id = doc.get("parent_thread_id")
        child_id = doc.get("thread_id")
        if parent_id and child_id:
            children_by_parent.setdefault(parent_id, []).append(child_id)

    pending = [normalized_thread_id]
    deleted_ids: List[str] = []
    while pending:
        current_id = pending.pop()
        if current_id in deleted_ids:
            continue
        deleted_ids.append(current_id)
        pending.extend(children_by_parent.get(current_id, []))

    await db.assistant_thread_messages.delete_many({
        "user_id": user_id,
        "thread_id": {"$in": deleted_ids},
    })
    await db.assistant_thread_checkpoints.delete_many({
        "user_id": user_id,
        "thread_id": {"$in": deleted_ids},
    })
    await db.assistant_threads.delete_many({
        "user_id": user_id,
        "thread_id": {"$in": deleted_ids},
    })

    return deleted_ids


async def get_assistant_thread_messages(
    db,
    user_id: str,
    conversation_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
    messages: List[Dict[str, Any]] = []
    cursor = db.assistant_thread_messages.find({
        "user_id": user_id,
        "thread_id": thread["thread_id"],
    }).sort("created_at", 1)
    async for doc in cursor:
        messages.append({
            "role": doc.get("role", "assistant"),
            "content": doc.get("content", ""),
            "tools_used": doc.get("tools_used") or None,
        })
    return _thread_doc_to_item(thread), messages


async def append_assistant_message(
    db,
    user_id: str,
    role: str,
    content: str,
    conversation_id: Optional[str] = None,
    tools_used: Optional[List[str]] = None,
) -> str:
    thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
    thread_id = thread["thread_id"]
    text = (content or "").strip()
    if not text:
        return thread_id

    await db.assistant_thread_messages.insert_one({
        "message_id": f"msg_{uuid.uuid4().hex}",
        "thread_id": thread_id,
        "user_id": user_id,
        "role": role,
        "content": text,
        "tools_used": tools_used or [],
        "created_at": _now_utc(),
    })

    updates: Dict[str, Any] = {"updated_at": _now_utc()}
    if role == "user":
        updates["last_user_message"] = text[:200]

    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": thread_id},
        {
            "$set": updates,
            "$inc": {"message_count": 1},
        },
    )
    return thread_id


async def summarize_assistant_thread(
    db,
    user_id: str,
    conversation_id: Optional[str] = None,
    summary_type: str = "manual",
) -> Dict[str, Any]:
    thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
    _, messages = await get_assistant_thread_messages(db, user_id, thread["thread_id"])
    summary = await _build_thread_summary_with_llm(db, messages[-12:], thread.get("title") or "")
    now = _now_utc()

    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": thread["thread_id"]},
        {
            "$set": {
                "current_summary": summary,
                "updated_at": now,
            }
        },
    )

    await db.assistant_thread_checkpoints.insert_one({
        "checkpoint_id": f"chk_{uuid.uuid4().hex[:12]}",
        "thread_id": thread["thread_id"],
        "user_id": user_id,
        "summary_type": summary_type,
        "summary_text": summary.get("abstract", ""),
        "structured_summary": summary,
        "created_at": now,
    })

    await _store_thread_summary_memory(
        db,
        user_id=user_id,
        thread_id=thread["thread_id"],
        title=thread.get("title") or "",
        summary=summary,
        summary_type=summary_type,
    )

    return summary


async def _store_thread_summary_memory(
    db,
    *,
    user_id: str,
    thread_id: str,
    title: str,
    summary: Dict[str, Any],
    summary_type: str,
) -> None:
    """Topic summaries are only retained in the Mongo thread summary collection and are no longer written to mem0 long-term memory."""
    return


async def save_assistant_message(
    db,
    user_id: str,
    user_content: str,
    assistant_content: str,
    tools_used: List[str],
    conversation_id: Optional[str] = None,
) -> None:
    """Write session appends to MongoDB.

    Message persistence synchronization is completed (the user must be able to see this round of conversation when refreshing the page);
    Topic summary (used for sidebar cards, LLM generation and failure are summarized with rule summaries) changed to background tasks.
    Never block reply returns——Historical lessons: When the coding endpoint occasionally responds slowly, it will time out in 45 seconds. × 3 times
    Exponential backoff retries keep users waiting for about 2.5 minutes for a pure display maintenance task.
    """
    thread_id = await append_assistant_message(
        db,
        user_id=user_id,
        role="user",
        content=user_content,
        conversation_id=conversation_id,
    )
    await append_assistant_message(
        db,
        user_id=user_id,
        role="assistant",
        content=assistant_content,
        conversation_id=thread_id,
        tools_used=tools_used,
    )
    _schedule_thread_summary(db, user_id, thread_id)


def _schedule_thread_summary(db, user_id: str, thread_id: str) -> None:
    """Generate thread summaries in the background (fire-and-forget).

    You must cover all exceptions yourself: create_task exceptions will be thrown if no one consumes them
    "Task exception was never retrieved"。
    """
    async def _run() -> None:
        try:
            await summarize_assistant_thread(
                db,
                user_id=user_id,
                conversation_id=thread_id,
                summary_type="auto",
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("[Smart Assistant Summary] Background summary task failed (does not affect session): %s", exc)

    try:
        asyncio.create_task(_run())
    except RuntimeError:
        # No running event loop (extreme scenario): The summary is a discardable display task, skip it directly
        logger.debug("[Smart Assistant Summary] No event loop, skip this round of background summary")


async def get_assistant_conversation(
    db,
    user_id: str,
    conversation_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Get the user s smart assistant session history"""
    _, messages = await get_assistant_thread_messages(db, user_id, conversation_id)
    return messages


async def clear_assistant_conversation(
    db,
    user_id: str,
    conversation_id: Optional[str] = None,
) -> None:
    """清空用户的智能助手会话"""
    thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
    await db.assistant_thread_messages.delete_many(
        {"user_id": user_id, "thread_id": thread["thread_id"]}
    )
    await db.assistant_threads.update_one(
        {"user_id": user_id, "thread_id": thread["thread_id"]},
        {
            "$set": {
                "message_count": 0,
                "last_user_message": "",
                "current_summary": {
                    "abstract": "",
                    "confirmed_facts": [],
                    "open_questions": [],
                    "next_actions": [],
                    "focus_score": 0.0,
                },
                "updated_at": _now_utc(),
            }
        },
    )


async def load_user_profile(db, user_id: str) -> Optional[dict]:
    """Load user profiles from the assistant_user_profiles collection"""
    try:
        doc = await db.assistant_user_profiles.find_one({"user_id": user_id})
        return doc
    except Exception as e:
        logger.warning("[Smart Assistant] Failed to load user portrait: %s", e)
    return None


async def update_user_profile_with_analysis(
    db,
    user_id: str,
    symbol: str,
    name: str,
    conclusion: str,
    task_id: str,
) -> None:
    """
    After the analysis task is completed, the results are appended to the recently_analyzed list of the user portrait.
    Keep the latest 20 profiles and write them into the assistant_user_profiles collection in upsert mode.
    """
    try:
        now = datetime.now(timezone.utc)
        entry = {
            "symbol": symbol,
            "name": name,
            "analyzed_at": now.strftime("%Y-%m-%d"),
            "conclusion": conclusion,
            "task_id": task_id,
        }
        await db.assistant_user_profiles.update_one(
            {"user_id": user_id},
            {
                "$push": {
                    "recently_analyzed": {
                        "$each": [entry],
                        "$slice": -20,
                    }
                },
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
        logger.info(f"[用户画像] ✅ 已更新 {user_id} 的 recently_analyzed: {symbol}({name})")
    except Exception as e:
        logger.warning(f"[User portrait] Update failed (ignored): {e}")


async def _load_assistant_settings(db, user_id: str) -> Optional[dict]:
    """Load the user s assistant personalization settings from the database"""
    try:
        from bson import ObjectId
        user_doc = await db.users.find_one(
            {"_id": ObjectId(user_id)},
            {"preferences.assistant_settings": 1},
        )
        if user_doc:
            prefs = user_doc.get("preferences", {})
            return prefs.get("assistant_settings")
    except Exception as e:
        logger.warning("[Smart Assistant] Failed to load assistant settings: %s", e)
    return None


# ------------------------------------------------------------------
#  mem0 unified memory layer — Assistant conversation integration
# ------------------------------------------------------------------

async def _recall_memory_block(db, user_id: str, user_message: str) -> str:
    """Recall the memory related to the current user/question from mem0, formatted into text that can be injected into prompt.

    Recall scope:
    - user_preference: User preferences (explicitly registered via remember_this)
    - trade_pattern:   Trading discipline memory (written after review is completed)
    """
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        return await svc.recall_formatted(
            query=user_message,
            user_id=user_id,
            scopes=["user_preference", "trade_pattern"],
            limit=6,
            max_chars=800,
        )
    except Exception as e:
        logger.debug("[mem0] Memory recall failed (ignored): %s", e)
        return ""


async def chat_with_assistant(
    db,
    user_message: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    current_thread_id: Optional[str] = None,
    is_im: bool = False,
    model: Optional[str] = None,
    model_config_id: Optional[str] = None,
    quick_model: Optional[str] = None,
    quick_model_config_id: Optional[str] = None,
    deep_model: Optional[str] = None,
    deep_model_config_id: Optional[str] = None,
    assistant_role: str = "general",
    user_context: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Convenience functions: Use smart assistants to have conversations
    user_id: Used to persist the session; if provided, the session will be saved after the session
    is_im: Whether it comes from IM channel (QQ Bot, etc.), when it is True, inject the mobile terminal format specification
    assistant_role: assistant role general=General Analysis Assistant / usage_helper=Use a Q&A bot
    user_context: Frontend context (only used in usage_helper mode)
    """
    # Set the user context for the assistant_ops tool to obtain the current user
    if user_id:
        set_current_user_id(user_id)
    if current_thread_id:
        set_current_assistant_thread_id(current_thread_id)
    elif conversation_id:
        set_current_assistant_thread_id(conversation_id)

    # Load user assistant personalization settings
    assistant_settings = None
    if user_id:
        assistant_settings = await _load_assistant_settings(db, user_id)

    # Load user portrait (persistent memory across sessions)
    user_profile: Optional[dict] = None
    current_topic_title: Optional[str] = None
    if user_id:
        try:
            user_profile = await load_user_profile(db, user_id)
            if user_profile and user_profile.get("recently_analyzed"):
                logger.info(f"[智能助手] ✅ 用户画像加载成功，最近分析 {len(user_profile['recently_analyzed'])} 条")
        except Exception as e:
            logger.warning(f"[Smart Assistant] Failed to load user portrait (skipped): {e}")

    if user_id and current_thread_id:
        try:
            current_topic = await db.assistant_threads.find_one(
                {
                    "user_id": user_id,
                    "thread_id": current_thread_id,
                    "archived": {"$ne": True},
                },
                {"title": 1},
            )
            if current_topic:
                current_topic_title = (current_topic.get("title") or "").strip() or None
        except Exception as e:
            logger.warning(f"[Smart Assistant] Failed to load current theme (skipped): {e}")

    # Load recent session history (up to 10, injected into LLM context)
    history_messages: Optional[List[Message]] = None
    if user_id:
        try:
            raw_history = await get_assistant_conversation(db, user_id, conversation_id)
            if raw_history:
                recent = raw_history[-ASSISTANT_MAX_CONTEXT_MESSAGES:]
                history_messages = []
                for m in recent:
                    role = MessageRole.USER if m.get("role") == "user" else MessageRole.ASSISTANT
                    content = (m.get("content") or "").strip()
                    if content:
                        history_messages.append(Message(role=role, content=content[:800]))
                if not history_messages:
                    history_messages = None
        except Exception as e:
            logger.warning(f"[Smart Assistant] Failed to load history session (skipped): {e}")

    # mem0 Memory recall (downgrade safety)
    memory_block = ""
    if user_id:
        memory_block = await _recall_memory_block(db, user_id, user_message)

    service = IntelligentAssistantService(
        db,
        preferred_models=_build_assistant_model_preferences(
            model=model,
            model_config_id=model_config_id,
            quick_model=quick_model,
            quick_model_config_id=quick_model_config_id,
            deep_model=deep_model,
            deep_model_config_id=deep_model_config_id,
        ),
        user_id=user_id or "",
        assistant_role=assistant_role,
        user_context=user_context,
    )
    result = await service.chat(
        user_message,
        conversation_id,
        assistant_settings,
        is_im=is_im,
        history_messages=history_messages,
        user_profile=user_profile,
        current_topic_title=current_topic_title,
        memory_block=memory_block,
    )
    if user_id and user_message.strip():
        # Empty replies (exception/timeout, etc.) are also saved: user questions cannot be lost due to failure
        assistant_content = (result.get("reply") or "").strip() or "⚠️ Reply generation failed for this round (no content received)"
        try:
            await save_assistant_message(
                db,
                user_id=user_id,
                user_content=user_message.strip(),
                assistant_content=assistant_content,
                tools_used=result.get("tools_used") or [],
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.warning("[Smart Assistant] Failed to save session: %s", e)

        # Note: mem0 conversation scope is deprecated and conversations are no longer automatically written to long-term memory.
        # User preferences via `remember_this` Explicit registration of meta-tools, see mem0 §15.5 P0-1. 
    if user_id:
        thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
        result["conversation_id"] = thread["thread_id"]
    return result


async def stream_chat_with_assistant(
    db,
    user_message: str,
    user_id: Optional[str] = None,
    conversation_id: Optional[str] = None,
    current_thread_id: Optional[str] = None,
    model: Optional[str] = None,
    model_config_id: Optional[str] = None,
    quick_model: Optional[str] = None,
    quick_model_config_id: Optional[str] = None,
    deep_model: Optional[str] = None,
    deep_model_config_id: Optional[str] = None,
    assistant_role: str = "general",
    user_context: Optional[dict] = None,
) -> AsyncGenerator[str, None]:
    """
    Streaming convenience functions: Use intelligent assistants for streaming conversations, async generators that return SSE event strings.
    assistant_role: assistant role general=General Analysis Assistant / usage_helper=Use a Q&A bot
    user_context: Frontend context (only used in usage_helper mode)
    """
    def _sse(event: str, data: dict) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    if user_id:
        set_current_user_id(user_id)
    if current_thread_id:
        set_current_assistant_thread_id(current_thread_id)
    elif conversation_id:
        set_current_assistant_thread_id(conversation_id)

    assistant_settings = None
    if user_id:
        assistant_settings = await _load_assistant_settings(db, user_id)

    user_profile: Optional[dict] = None
    current_topic_title: Optional[str] = None
    if user_id:
        try:
            user_profile = await load_user_profile(db, user_id)
        except Exception:
            pass

    if user_id and (current_thread_id or conversation_id):
        tid = current_thread_id or conversation_id
        try:
            current_topic = await db.assistant_threads.find_one(
                {"user_id": user_id, "thread_id": tid, "archived": {"$ne": True}},
                {"title": 1},
            )
            if current_topic:
                current_topic_title = (current_topic.get("title") or "").strip() or None
        except Exception:
            pass

    history_messages: Optional[List[Message]] = None
    if user_id:
        try:
            raw_history = await get_assistant_conversation(db, user_id, conversation_id)
            if raw_history:
                recent = raw_history[-ASSISTANT_MAX_CONTEXT_MESSAGES:]
                history_messages = []
                for m in recent:
                    role = MessageRole.USER if m.get("role") == "user" else MessageRole.ASSISTANT
                    content = (m.get("content") or "").strip()
                    if content:
                        history_messages.append(Message(role=role, content=content[:800]))
                if not history_messages:
                    history_messages = None
        except Exception:
            pass

    # mem0 memory recall
    memory_block = ""
    if user_id:
        memory_block = await _recall_memory_block(db, user_id, user_message)

    logger.info("[Smart Assistant·streaming] mem0 Recall completed, memory_block length=%d, ready to create service", len(memory_block))

    service = IntelligentAssistantService(
        db,
        preferred_models=_build_assistant_model_preferences(
            model=model,
            model_config_id=model_config_id,
            quick_model=quick_model,
            quick_model_config_id=quick_model_config_id,
            deep_model=deep_model,
            deep_model_config_id=deep_model_config_id,
        ),
        user_id=user_id or "",
        assistant_role=assistant_role,
        user_context=user_context,
    )

    collected_reply = ""
    collected_tools: List[str] = []
    collected_data_refs: List[Dict[str, Any]] = []
    error_note = ""  # Error description for this round (inner timeout/exception/cancellation, or outer generator exception), dropped with the session

    logger.info("[Smart Assistant·streaming] ready to call service.chat_stream")

    try:
        async for event_str in service.chat_stream(
            user_message,
            conversation_id,
            assistant_settings,
            history_messages=history_messages,
            user_profile=user_profile,
            current_topic_title=current_topic_title,
            memory_block=memory_block,
        ):
            if event_str.startswith("event: done\n"):
                try:
                    data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                    data = json.loads(data_line)
                    collected_tools = data.get("tools_used", [])
                    collected_data_refs = data.get("data_refs", [])
                except Exception:
                    pass
                continue
            if event_str.startswith("event: token\n"):
                try:
                    data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                    data = json.loads(data_line)
                    collected_reply += data.get("content", "")
                except Exception:
                    pass
            elif event_str.startswith("event: error\n"):
                # Record internal errors (timeout/exception/cancellation) and log them into the database with the session to facilitate subsequent troubleshooting.
                try:
                    data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                    data = json.loads(data_line)
                    if data.get("message"):
                        error_note = str(data["message"])
                except Exception:
                    pass
            yield event_str
    except Exception as e:
        logger.error("[Smart Assistant·streaming] chat_stream Generator throws exception: %s", e, exc_info=True)
        error_note = f"An exception occurred during processing:{e}"
        # Send an error event to let the front end clearly perceive the failure (instead of disguising the exception as a reply text)
        yield _sse("error", {"message": error_note})
    finally:
        # Session persistence is guaranteed: regardless of normal end, internal error or client disconnection,
        # User questions must be logged into the database, and some of the generated responses and error descriptions must also be logged into the database.
        # Historical lessons: Originally, it was only saved when "reply to complete collection" and refreshed after timeout/interruption.
        # Questions asked by users on the page disappear directly.——Without the context, there is no way to find out what went wrong at the time.
        if user_id and user_message.strip():
            assistant_content = collected_reply.strip()
            if error_note:
                assistant_content = (
                    f"{assistant_content}\n\n---\n⚠️ {error_note}"
                    if assistant_content
                    else f"⚠️ {error_note}"
                )
            if not assistant_content:
                assistant_content = "⚠️ Reply generation failed for this round (no content received)"
            try:
                await save_assistant_message(
                    db,
                    user_id=user_id,
                    user_content=user_message.strip(),
                    assistant_content=assistant_content,
                    tools_used=collected_tools,
                    conversation_id=conversation_id,
                )
            except Exception as e:
                logger.warning("[Smart Assistant·streaming] Failed to save session: %s", e)

        # Note: mem0 conversation scope is deprecated and conversations are no longer automatically written to long-term memory.
        # User preferences via `remember_this` Explicit registration of meta-tools, see mem0 §15.5 P0-1. 

    conv_id = conversation_id
    if user_id:
        thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
        conv_id = thread["thread_id"]

    yield _sse("done", {
        "tools_used": collected_tools,
        "data_refs": collected_data_refs,
        "conversation_id": conv_id,
        **({"error": True} if error_note else {}),
    })
