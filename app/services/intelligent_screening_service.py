"""
Intelligent screening service — LLM Multiple rounds of dialogue stock selection

Reuse the LLM configuration, tool registry, timeout mechanism and other infrastructure of the intelligent assistant,
Added two-stage process (requirement confirmation → perform screening) and multiple rounds of memorization.
"""

import asyncio
import inspect
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

# Reuse the infrastructure of smart assistants
from app.services.factor_registry_service import build_screening_fields_markdown
from app.services.screening_metric_display import resolve_metric_value, select_metric_display_spec
from app.services.intelligent_assistant_service import (
    _get_assistant_llm_config,
    _get_latest_trade_date,
    ASSISTANT_TIMEOUT_SECONDS,
)
from core.tools import get_tool_registry, tool_metadata_list_to_openai
from core.tools.context import set_current_user_id
from core.tools.implementations.market.stock_screening_tool import _execute_screening_query, _format_screening_output
from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole

logger = logging.getLogger(__name__)

# Maximum number of session history items (per user)
SCREENING_CONVERSATION_LIMIT = 50
# The maximum number of historical messages sent to LLM per request
MAX_CONTEXT_MESSAGES = 20
# Tool categories related to stock picking
# "screening" Category Contains screen_stocks_by_criteria Batch Filter Tool (Core)
SCREENING_TOOL_CATEGORIES = ["screening", "market", "fundamentals", "news", "china", "technical"]
SCREENING_TOOL_IDS = {
    "add_stocks_to_favorites",
    "list_watchlist_groups",
    "add_stock_to_watchlist",
}

# Tool convergence in the execution phase: Prioritize only allowing batch screening of links to avoid single-strand heavy tool amplification delays
RESULT_TOOL_ALLOWLIST = {
    "screen_stocks_by_criteria",
    "batch_check_profit_consistency",
    "add_stocks_to_favorites",
    "list_watchlist_groups",
    "add_stock_to_watchlist",
}

# Independent budget for stock selection scenarios, tighter than the global assistant by default, to avoid long-tail requests from dragging down the experience
SCREENING_MAX_TOOL_ROUNDS = int(os.environ.get("SCREENING_MAX_TOOL_ROUNDS", "3"))
SCREENING_RESULT_TIMEOUT_SECONDS = int(os.environ.get("SCREENING_RESULT_TIMEOUT_SECONDS", "300"))

SCREENING_ADJUST_KEYWORDS = [
    "重新",
    "修改",
    "调整需求",
    "换个",
    "不对",
    "重新描述",
    "重新考虑",
    "再低点",
    "再高点",
    "缩小",
    "放宽",
]

SCREENING_APPROVAL_KEYWORDS = [
    "执行筛选方案",
    "按此方案",
    "开始筛选",
    "执行",
    "同意",
    "确认",
    "按原需求筛选",
]

SCREENING_NEW_REQUEST_KEYWORDS = [
    "帮我选",
    "选几只",
    "筛选",
    "选股",
    "推荐几只",
    "找几只",
    "高分红",
    "低估值",
    "股票",
]

SCREENING_RESULT_REFERENCE_KEYWORDS = [
    "这5只",
    "这五只",
    "这几只",
    "这些股票",
    "刚才那5只",
    "刚才推荐",
    "当前推荐",
    "上一轮",
    "加入自选",
    "加入股票关注列表",
    "打标签",
    "分组",
]

SCREENING_MULTI_STOCK_REQUEST_KEYWORDS = [
    "帮我选",
    "筛选",
    "推荐几只",
    "找几只",
    "候选",
    "组合",
]

SINGLE_STOCK_QUERY_PREFIXES = (
    "请问一下",
    "请问",
    "我想问一下",
    "我想问",
    "想问一下",
    "想问",
    "帮我看下",
    "帮我判断一下",
    "麻烦看下",
    "麻烦问下",
)

SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD = 3.0

SCREENING_FIELD_DISPLAY_LABELS = {
    "industry": "行业",
    "dividend_yield": "股息率",
    "pe": "PE",
    "pe_ttm": "PE(TTM)",
    "pb": "PB",
    "pb_mrq": "PB(MRQ)",
    "roe": "ROE",
    "roa": "ROA",
    "gross_margin": "毛利率",
    "netprofit_margin": "净利率",
    "debt_to_assets": "资产负债率",
    "assets_to_eqt": "权益乘数",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "cash_ratio": "现金比率",
    "total_mv": "总市值",
    "close": "股价",
    "pct_chg": "涨跌幅",
    "report_period": "财报期",
    "n_cashflow_act": "经营现金流",
    "revenue_ttm": "营收TTM",
    "net_profit_ttm": "净利TTM",
}

SCREENING_PERCENT_FIELDS = {
    "dividend_yield",
    "roe",
    "roa",
    "gross_margin",
    "netprofit_margin",
    "debt_to_assets",
    "pct_chg",
}

SCREENING_YI_FIELDS = {"n_cashflow_act", "revenue_ttm", "net_profit_ttm"}


class IntelligentScreeningService:
    """
    Intelligent screening service — LLM Multiple rounds of dialogue stock selection

    Reuse the LLM configuration, tool registry, timeout mechanism and other infrastructure of the intelligent assistant,
    Added two-stage process (requirement confirmation → perform screening) and multiple rounds of memorization.
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._openai_tools: Optional[list] = None
        self._result_openai_tools: Optional[list] = None
        self._tool_functions: Optional[dict] = None

    async def _ensure_client(self) -> bool:
        """Lazy loading of LLM clients and tools (only 5 types of tools related to stock selection are loaded)"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(self._db)
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
        except Exception as e:
            logger.error(f"[Smart filtering] Creating LLM client failed: {e}", exc_info=True)
            return False

        # Only load tools related to stock selection
        registry = get_tool_registry()
        all_metadata = registry.list_all()
        screening_metadata = [
            m for m in all_metadata
            if m.fc_enabled and (m.category in SCREENING_TOOL_CATEGORIES or m.id in SCREENING_TOOL_IDS)
        ]
        self._openai_tools = tool_metadata_list_to_openai(screening_metadata)

        self._tool_functions = {}
        for tool in screening_metadata:
            if tool.parameters:
                func = registry.get_function(tool.id)
                if func:
                    self._tool_functions[tool.id] = func

        # In the results execution phase, only tools related to batch screening are retained to limit the complexity of the tool chain.
        self._result_openai_tools = self._filter_result_tools(self._openai_tools)
        if not self._result_openai_tools:
            self._result_openai_tools = self._openai_tools
            logger.warning("[Smart filtering] In the result stage, the batch tool whitelist is empty and falls back to the complete tool set.")

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(
            f"[智能筛选] 已加载 {len(self._openai_tools)} 个选股工具，"
            f"Used in the results phase {len(self._result_openai_tools)} execution tools"
        )
        return True

    def _filter_result_tools(self, openai_tools: Optional[list]) -> list:
        """The tools available in the filtering result stage give priority to retaining batch filtering links."""
        if not openai_tools:
            return []

        filtered = []
        for t in openai_tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            name = fn.get("name")
            if name in RESULT_TOOL_ALLOWLIST:
                filtered.append(t)
        return filtered

    def _infer_request_focus(self, message: str) -> str:
        """Extract core filtering requirements from user requests for no-result and downgrade prompts."""
        text = (message or "").strip()
        if not text:
            return "原筛选条件"

        focus_keywords = [
            ("高分红", ["高分红", "分红", "股息", "股息率", "dividend"]),
            ("低估值", ["低估值", "低pe", "低 pb", "低pb", "估值低", "便宜"]),
            ("银行股", ["银行"]),
            ("消费股", ["消费"]),
            ("科技股", ["科技", "芯片", "半导体", "ai"]),
            ("高ROE", ["roe"]),
        ]
        lower_text = text.lower()
        for label, keywords in focus_keywords:
            if any(keyword in text or keyword in lower_text for keyword in keywords):
                return label
        return "原筛选条件"

    def _extract_single_stock_keyword(self, message: str) -> Optional[str]:
        """Extract stock symbols or abbreviations from single stock judgment questions."""
        text = re.sub(r"\s+", "", message or "")
        if not text:
            return None

        code_match = re.search(r"(?<!\d)(\d{6})(?!\d)", text)
        if code_match:
            return code_match.group(1)

        normalized = text
        for prefix in SINGLE_STOCK_QUERY_PREFIXES:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break

        normalized = re.sub(r"[？?！!。,.，：:；;]", "", normalized)
        patterns = [
            r"([A-Za-z\u4e00-\u9fa5]{2,16})(?:\(| ()?(?:\d{6})?(?:\)|) )?(?:Isn t it|Whether|Does it count?|does not belong to|Belong to|Yes)",
            r"([A-Za-z\u4e00-\u9fa5]{2,16})(?:\(| ()?(?:\d{6})?(?:\)|) )?(?:of)?(?:dividend yield|dividend)",
        ]
        stopwords = {"这个", "这只", "该股", "股票", "A股", "个股"}
        for pattern in patterns:
            match = re.search(pattern, normalized)
            if not match:
                continue
            keyword = match.group(1).strip()
            if keyword in stopwords or len(keyword) < 2:
                continue
            return keyword

        return None

    def _looks_like_single_stock_judgement_query(self, message: str) -> bool:
        """identify Whether a single stock meets a certain attribute of direct judgment."""
        text = re.sub(r"\s+", "", message or "")
        if not text:
            return False

        if self._is_adjustment_message(text) or self._is_approval_message(text):
            return False

        if any(keyword in text for keyword in SCREENING_MULTI_STOCK_REQUEST_KEYWORDS):
            return False

        if self._infer_request_focus(text) != "高分红":
            return False

        if not self._extract_single_stock_keyword(text):
            return False

        return any(token in text for token in ("是不是", "是否", "算不算", "属于", "是", "吗"))

    async def _fetch_single_stock_item(self, keyword: str) -> Optional[dict]:
        """Retrieve the best matching single stock snapshot by symbol or name."""
        items, _total = await _execute_screening_query(
            [{"field": "keyword", "operator": "contains", "value": keyword}],
            10,
            "total_mv",
            "desc",
        )
        if not items:
            return None

        normalized = keyword.strip().lower()

        def score(item: dict) -> tuple[int, float]:
            code = str(item.get("code") or item.get("symbol") or "").strip().lower()
            name = str(item.get("name") or "").strip().lower()
            item_score = 0
            if normalized == code:
                item_score += 100
            if normalized == name:
                item_score += 95
            if normalized and normalized in name:
                item_score += 80
            if normalized and normalized in code:
                item_score += 70
            return item_score, float(item.get("total_mv") or 0)

        return max(items, key=score)

    def _build_single_stock_snapshot(self, item: dict, reason: str) -> dict[str, Any]:
        pe_order_field = "pe_ttm" if item.get("pe_ttm") is not None else "pe"
        pb_order_field = "pb_mrq" if item.get("pb_mrq") is not None else "pb"
        pe_display_field, pe_display_label = select_metric_display_spec(None, pe_order_field, "pe")
        pb_display_field, pb_display_label = select_metric_display_spec(None, pb_order_field, "pb")
        code = str(item.get("code") or item.get("symbol") or "").strip()

        return {
            "code": code,
            "name": str(item.get("name") or ""),
            "industry": str(item.get("industry") or ""),
            "price": item.get("close"),
            "pe": resolve_metric_value(item, pe_display_field, "pe"),
            "pe_display_label": pe_display_label,
            "pb": resolve_metric_value(item, pb_display_field, "pb"),
            "pb_display_label": pb_display_label,
            "roe": item.get("roe"),
            "roa": item.get("roa"),
            "gross_margin": item.get("gross_margin"),
            "netprofit_margin": item.get("netprofit_margin"),
            "dividend_yield": item.get("dividend_yield"),
            "debt_to_assets": item.get("debt_to_assets"),
            "assets_to_eqt": item.get("assets_to_eqt"),
            "current_ratio": item.get("current_ratio"),
            "quick_ratio": item.get("quick_ratio"),
            "cash_ratio": item.get("cash_ratio"),
            "revenue_ttm": item.get("revenue_ttm"),
            "net_profit_ttm": item.get("net_profit_ttm"),
            "n_cashflow_act": item.get("n_cashflow_act"),
            "report_period": item.get("report_period"),
            "pct_change": item.get("pct_chg"),
            "reason": reason,
        }

    async def _maybe_handle_single_stock_query(
        self,
        message: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Directly return results for single stock attribute judgment questions to avoid entering the market-wide screening process by mistake."""
        if not self._looks_like_single_stock_judgement_query(message):
            return None

        await self._emit_progress(
            progress_callback,
            "status",
            phase="result",
            message="Checking the dividend index of a single stock",
        )

        keyword = self._extract_single_stock_keyword(message)
        if not keyword:
            return None

        item = await self._fetch_single_stock_item(keyword)
        if not item:
            reply = f"未找到与“{keyword}”匹配的股票，暂时无法判断它是否属于高分红股票。"
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "is_fallback": False,
            }

        stock_name = str(item.get("name") or keyword)
        stock_code = str(item.get("code") or item.get("symbol") or "")
        dividend_yield = item.get("dividend_yield")
        if not isinstance(dividend_yield, (int, float)):
            reply = f"已找到 {stock_name}（{stock_code}），但当前快照里没有可用的股息率数据，暂时无法判断它是否属于高分红股票。"
            stock = self._build_single_stock_snapshot(item, "There is currently a lack of available dividend yield data, so it is impossible to directly determine whether it is a high dividend payout.")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [stock],
                "phase": "result",
                "is_fallback": False,
            }

        is_high_dividend = dividend_yield >= SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD
        verdict = "可以算" if is_high_dividend else "严格按当前默认口径暂不算"
        reason = (
            f"Single stock verification: the default is based on the dividend rate of the past 12 months ≥ {SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD:.1f}% As a high dividend caliber;"
            f"current dividend yield={dividend_yield:.2f}%, Therefore{verdict}High dividends."
        )
        stock = self._build_single_stock_snapshot(item, reason)

        metrics: list[str] = [f"股息率={dividend_yield:.2f}%"]
        if isinstance(stock.get("pe"), (int, float)):
            metrics.append(f"{stock.get('pe_display_label') or 'PE'}={stock['pe']:.2f}")
        if isinstance(stock.get("roe"), (int, float)):
            metrics.append(f"ROE={stock['roe']:.2f}%")
        if stock.get("report_period"):
            metrics.append(f"财报期={stock['report_period']}")

        reply_lines = [
            f"Conclusion:{stock_name} ({stock_code}) {verdict}High dividend stocks.",
            f"Judgment criteria: If no additional threshold is specified, this system defaults to the dividend rate of the past 12 months ≥ {SINGLE_STOCK_DIVIDEND_YIELD_THRESHOLD:.1f}% Considered a high dividend.",
            f"Current indicators:{'; '.join(metrics)}. ",
        ]
        if is_high_dividend:
            reply_lines.append("Additional explanation: It is closer to a high-quality white horse that pays stable dividends, and is not the same as a dividend target with the highest dividend yield in the market.")
        else:
            reply_lines.append("Supplementary note: If you are more concerned about dividend stability or dividend ratio rather than the static dividend rate threshold, you can use this caliber to make your judgment.")

        return {
            "reply": "\n\n".join(reply_lines),
            "tools_used": [],
            "stocks": [stock],
            "phase": "result",
            "is_fallback": False,
        }

    def _build_no_match_reply(self, message: str) -> str:
        """A hard tip is returned when the condition is not hit, and no alternative stocks are recommended."""
        focus = self._infer_request_focus(message)
        return (
            f"未找到符合“{focus}”条件的股票。\n\n"
            "There is currently no target that meets the screening requirements, and other stocks that do not meet the conditions are not recommended."
            "If you still want to continue filtering, please further add thresholds, narrow the industry scope, or adjust the filtering conditions and try again."
        )

    def _build_timeout_reply(self, timeout_seconds: int) -> str:
        """A hard prompt is returned when execution times out and no alternative stocks are recommended."""
        return (
            f"Sorry, processing your stock selection request has timed out (more than {timeout_seconds} seconds).\n\n"
            "This time we will not recommend other stocks that do not meet the original screening conditions."
            "It is recommended that you narrow the filter scope, add more specific thresholds or industry conditions, or try again later."
        )

    def _find_last_assistant(self, history: list) -> Optional[dict]:
        for msg in reversed(history or []):
            if msg.get("role") == "assistant":
                return msg
        return None

    async def _classify_intent(self, message: str, history: list) -> Dict[str, Any]:
        """
        Let LLM analyze user intent instead of hard-coding keywords.

        Return:
        {
            "intent": "adjustment" | "approval" | "new_request" | "follow_up" | "single_stock_query",
            "adjustment_target": "roe" | "pe" | "pb" | "margin" | "other" | null,
            "adjustment_direction": "loosen" | "tighten" | null,
            "explicit_parameters": str | null,
            "confidence": float
        }
        """
        if not await self._ensure_client():
            # If LLM is not available, fall back to keyword mode
            return {
                "intent": "adjustment" if self._is_adjustment_message(message) else
                          "approval" if self._is_approval_message(message) else
                          "new_request" if self._looks_like_new_screening_request(message) else
                          "single_stock_query" if self._looks_like_single_stock_judgement_query(message) else
                          "follow_up",
                "adjustment_target": None,
                "adjustment_direction": None,
                "explicit_parameters": None,
                "confidence": 0.5
            }

        history_summary = ""
        if history:
            recent = history[-4:]  # The last 4 items are enough to understand the context
            for h in recent:
                role = "用户" if h["role"] == "user" else "助手"
                content = h["content"][:200] + "..." if len(h["content"]) > 200 else h["content"]
                history_summary += f"{role}: {content}\n"

        system_prompt = """You are an intent classifier. Please analyze the user s latest news and combine it with the conversation history to determine the user s intention.

Return JSON format:
{
    "intent": "adjustment" | "approval" | "new_request" | "follow_up" | "single_stock_query",
    "adjustment_target": "roe" | "pe" | "pb" | "margin" | "debt" | "cashflow" | "other" | null,
    "adjustment_direction": "loosen" | "tighten" | null,
    "explicit_parameters": "Specific parameters explicitly mentioned by the user, e.g.'Relax ROE to 10%'in'10%'" | null,
    "confidence": 0.0-1.0 confidence level between
}

Intent definition:
- adjustment: The user wants to adjust the previous filtering conditions (relax, tighten, modify, etc.)
- approval: The user explicitly approves a plan ("execute", "According to this plan", "OK"etc.)
- new_request: Users have put forward new stock selection needs, which have little to do with the previous screening.
- follow_up: The user asks based on the current results ("How about these ones?", "Add to your choice"etc.)
- single_stock_query: User asks about a single stock

adjustment_target: When intent=adjustment, indicate which indicator the user wants to adjust
adjustment_direction: When intent=adjustment when it is pointed out that it is relaxing(loosen)Still tighten(tighten)

Note:
- If the user says"Let s relax ROE first", intent=adjustment, adjustment_target=roe, adjustment_direction=loosen
- If the user says"Change PE to<20", intent=adjustment, adjustment_target=pe, adjustment_direction=loosen, explicit_parameters="20"
- If the user says"Execute screening plan", intent=approval
- If the user says"Help me choose technology stocks again", intent=new_request
- If the user says"Add these to your choice", intent=follow_up
- If the user asks"How about Kweichow Moutai?", intent=single_stock_query
"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=f"Conversation history:\n{history_summary}\n\n Latest user news:{message}")
        ]

        try:
            resp = await self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="intent_classification")
            content = resp.content if resp else ""
            # Extract JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', content)
            if json_match:
                result = json.loads(json_match.group(0))
                return result
        except Exception as e:
            logger.warning(f"[Smart filtering] Intent classification LLM call failed: {e}")

        # Fallback on failure
        return {
            "intent": "adjustment" if self._is_adjustment_message(message) else
                      "approval" if self._is_approval_message(message) else
                      "new_request" if self._looks_like_new_screening_request(message) else
                      "single_stock_query" if self._looks_like_single_stock_judgement_query(message) else
                      "follow_up",
            "adjustment_target": None,
            "adjustment_direction": None,
            "explicit_parameters": None,
            "confidence": 0.3
        }

    def _is_adjustment_message(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_ADJUST_KEYWORDS)

    def _is_approval_message(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_APPROVAL_KEYWORDS)

    def _looks_like_new_screening_request(self, message: str) -> bool:
        text = (message or "").strip()
        if not text:
            return False
        if self._is_adjustment_message(text) or self._is_approval_message(text):
            return False
        return any(keyword in text for keyword in SCREENING_NEW_REQUEST_KEYWORDS)

    def _references_latest_result(self, message: str) -> bool:
        text = (message or "").strip()
        return any(keyword in text for keyword in SCREENING_RESULT_REFERENCE_KEYWORDS)

    def _select_phase_history(self, history: list, phase: str, message: str, intent: Dict[str, Any] = None) -> list:
        """Compress history by stage to avoid the result stage continuing to inherit the entire old session."""
        recent_history = history[-MAX_CONTEXT_MESSAGES:]
        if not recent_history:
            return []

        # If it is an adjustment class, approval class, or follow-up message, keep the full history so LLM understands the context
        intent_type = intent.get("intent") if intent else None
        if intent_type in ["adjustment", "approval", "follow_up"]:
            return recent_history

        last_assistant = self._find_last_assistant(recent_history)
        if (
            phase == "confirmation"
            and last_assistant
            and last_assistant.get("phase") == "result"
            and intent_type == "new_request"
        ):
            return []

        if phase != "result":
            return recent_history

        selected_history: List[dict] = []
        latest_planning = None
        latest_result = None
        for item in reversed(recent_history):
            if item.get("role") != "assistant":
                continue
            item_phase = item.get("phase")
            if latest_result is None and item_phase == "result":
                latest_result = item
            if latest_planning is None and item_phase == "planning":
                latest_planning = item
            if latest_planning and latest_result:
                break

        if latest_planning:
            selected_history.append(latest_planning)
        if latest_result and intent_type == "follow_up":
            selected_history.append(latest_result)

        return selected_history or recent_history[-2:]

    def _extract_locked_execution_plan(self, history: list) -> Optional[dict]:
        """Extract approved batch execution parameters from the most recent planning reply."""
        latest_planning = None
        for item in reversed(history or []):
            if item.get("role") == "assistant" and item.get("phase") == "planning":
                latest_planning = item
                break

        if not latest_planning:
            return None

        content = str(latest_planning.get("content") or "")
        conditions_match = re.search(r"`?conditions`?\s*[:：]\s*`(\[[\s\S]*?\])`", content)
        limit_match = re.search(r"`?limit`?\s*[:：]\s*(\d+)", content)
        order_by_match = re.search(r'`?order_by_field`?\s*[:：]\s*"([^"]+)"', content)
        order_direction_match = re.search(r'`?order_direction`?\s*[:：]\s*"([^"]+)"', content)

        if not conditions_match:
            return None

        try:
            raw_conditions = json.loads(conditions_match.group(1))
        except json.JSONDecodeError:
            return None

        if not isinstance(raw_conditions, list) or not raw_conditions:
            return None

        plan: Dict[str, Any] = {
            "planning_content": content,
            "screen": {
                "conditions_json": json.dumps(raw_conditions, ensure_ascii=False),
                "limit": int(limit_match.group(1)) if limit_match else 50,
                "order_by_field": order_by_match.group(1) if order_by_match else "total_mv",
                "order_direction": order_direction_match.group(1) if order_direction_match else "desc",
            },
        }

        years_match = re.search(r"`?years`?\s*[:：]\s*(\d+)", content)
        threshold_match = re.search(r"`?threshold_cv`?\s*[:：]\s*([0-9.]+)", content)
        if years_match or threshold_match:
            plan["batch"] = {
                "years": int(years_match.group(1)) if years_match else 3,
                "threshold_cv": float(threshold_match.group(1)) if threshold_match else 0.3,
            }

        return plan

    def _extract_candidate_codes(self, screening_output: str) -> list[str]:
        match = re.search(r"Candidate code list (sorted by current, total\s*\d+\s*only):\s*([^\n]+)", screening_output or "")
        if not match:
            return []
        return [code.strip() for code in match.group(1).split(",") if code.strip()]

    def _build_locked_plan_summary(self, locked_plan: dict) -> str:
        screen_plan = locked_plan.get("screen", {})
        try:
            conditions = json.loads(screen_plan.get("conditions_json", "[]"))
        except json.JSONDecodeError:
            conditions = []

        lines = ["Summary of approved execution plan:"]
        if conditions:
            lines.append(f"- 筛选条件: {json.dumps(conditions, ensure_ascii=False)}")
        lines.append(f"- limit: {screen_plan.get('limit', 50)}")
        lines.append(f"- order_by_field: {screen_plan.get('order_by_field', 'total_mv')}")
        lines.append(f"- order_direction: {screen_plan.get('order_direction', 'desc')}")

        batch_plan = locked_plan.get("batch")
        if batch_plan:
            lines.append(
                f"- Profit stability verification: years={batch_plan.get('years', 3)}, "
                f"threshold_cv={batch_plan.get('threshold_cv', 0.3)}"
            )

        return "\n".join(lines)

    def _compact_screening_output_for_llm(self, screening_output: str) -> str:
        lines = [line for line in (screening_output or "").splitlines() if line.strip()]
        if not lines:
            return "No filter results."

        summary_lines: List[str] = [lines[0]]
        candidate_lines = [line for line in lines if re.match(r"^\d+\.\s", line)]
        summary_lines.extend(candidate_lines[:5])
        if len(candidate_lines) > 5:
            summary_lines.append(f"其余 {len(candidate_lines) - 5} 只候选已省略。")
        return "\n".join(summary_lines)

    def _compact_batch_output_for_llm(self, batch_output: str) -> str:
        lines = [line for line in (batch_output or "").splitlines() if line.strip()]
        if not lines:
            return "No profit stability verification was performed in this round."

        summary_lines = [lines[0]]
        summary_match = next((line for line in lines if line.startswith("📊 Summary:")), "")
        if summary_match:
            summary_lines.append(summary_match)

        stable_match = re.search(r"✅ Stable stock code:([^\n]+)", batch_output or "")
        if stable_match:
            stable_codes = [code.strip() for code in stable_match.group(1).split(",") if code.strip()]
            preview = ", ".join(stable_codes[:8])
            summary_lines.append(f"稳定股票代码预览: {preview}")
            if len(stable_codes) > 8:
                summary_lines.append(f"其余 {len(stable_codes) - 8} 只稳定股票代码已省略。")

        no_data_match = re.search(r"No data\s*(\d+)\s*only", batch_output or "")
        if no_data_match:
            summary_lines.append(f"无数据股票数量: {no_data_match.group(1)}")

        return "\n".join(summary_lines)

    def _extract_stable_codes(self, batch_output: str) -> list[str]:
        stable_match = re.search(r"✅ Stable stock code:([^\n]+)", batch_output or "")
        if not stable_match:
            return []
        return [code.strip() for code in stable_match.group(1).split(",") if code.strip()]

    def _format_reason_metric_value(self, field: str, value: Any) -> str:
        if value is None:
            return "-"
        if field in SCREENING_PERCENT_FIELDS and isinstance(value, (int, float)):
            return f"{value:.2f}%"
        if field in SCREENING_YI_FIELDS and isinstance(value, (int, float)):
            return f"{value / 1e8:.2f}亿"
        if field == "total_mv" and isinstance(value, (int, float)):
            return f"{value:.2f}亿"
        if field == "report_period":
            return str(value)
        if isinstance(value, (int, float)):
            return f"{value:.2f}"
        return str(value)

    def _get_reason_field_label(self, field: str, pe_display_label: str, pb_display_label: str) -> str:
        if field in {"pe", "pe_ttm"}:
            return pe_display_label
        if field in {"pb", "pb_mrq"}:
            return pb_display_label
        return SCREENING_FIELD_DISPLAY_LABELS.get(field, field)

    def _build_stock_reason(
        self,
        item: dict,
        raw_conditions: list,
        pe_display_field: str,
        pe_display_label: str,
        pb_display_field: str,
        pb_display_label: str,
        stability_checked: bool,
        stability_passed: bool,
    ) -> str:
        reason_parts: list[str] = []
        seen_parts: set[str] = set()

        for condition in raw_conditions:
            if not isinstance(condition, dict):
                continue
            field = condition.get("field")
            if field == "is_st" and condition.get("value") is False:
                if "非ST" not in seen_parts:
                    reason_parts.append("非ST")
                    seen_parts.add("非ST")
                continue

            if field == "keyword":
                continue

            if field in {"pe", "pe_ttm"}:
                value = resolve_metric_value(item, pe_display_field, "pe")
            elif field in {"pb", "pb_mrq"}:
                value = resolve_metric_value(item, pb_display_field, "pb")
            else:
                value = item.get(field)

            if value is None:
                continue

            label = self._get_reason_field_label(field, pe_display_label, pb_display_label)
            part = f"{label}={self._format_reason_metric_value(field, value)}"
            if part not in seen_parts:
                reason_parts.append(part)
                seen_parts.add(part)

        if not reason_parts:
            fallback_fields = [
                (pe_display_field, pe_display_label),
                (pb_display_field, pb_display_label),
                ("dividend_yield", "股息率"),
                ("roe", "ROE"),
                ("debt_to_assets", "资产负债率"),
            ]
            for field, label in fallback_fields:
                value = resolve_metric_value(item, field, "pe") if field in {"pe", "pe_ttm"} else resolve_metric_value(item, field, "pb") if field in {"pb", "pb_mrq"} else item.get(field)
                if value is None:
                    continue
                part = f"{label}={self._format_reason_metric_value(field, value)}"
                if part not in seen_parts:
                    reason_parts.append(part)
                    seen_parts.add(part)

        report_period = item.get("report_period")
        if report_period and "财报期" not in seen_parts:
            reason_parts.append(f"财报期={report_period}")

        if stability_checked:
            reason_parts.append("近3年盈利稳定性验证通过" if stability_passed else "This round was not included in the profit stability pass list")

        if not reason_parts:
            return "Matches approved filters."

        return "Meet approved conditions:" + "，".join(reason_parts[:5]) + "。"

    def _build_structured_stocks(
        self,
        items: list,
        raw_conditions: list,
        order_by_field: str,
        batch_output: str,
    ) -> list[dict[str, Any]]:
        pe_display_field, pe_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pe")
        pb_display_field, pb_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pb")
        stable_codes = self._extract_stable_codes(batch_output)
        stable_set = set(stable_codes)
        selected_items = items or []
        if stable_codes:
            stable_items = [
                item for item in selected_items
                if str(item.get("code") or item.get("symbol", "")).strip() in stable_set
            ]
            if stable_items:
                selected_items = stable_items

        stocks: list[dict[str, Any]] = []
        for item in selected_items[:5]:
            code = str(item.get("code") or item.get("symbol", "")).strip()
            if not code:
                continue

            stability_checked = bool(batch_output)
            stability_passed = code in stable_set if stable_set else False
            stocks.append({
                "code": code,
                "name": str(item.get("name") or ""),
                "industry": str(item.get("industry") or ""),
                "price": item.get("close"),
                "pe": resolve_metric_value(item, pe_display_field, "pe"),
                "pe_display_label": pe_display_label,
                "pb": resolve_metric_value(item, pb_display_field, "pb"),
                "pb_display_label": pb_display_label,
                "roe": item.get("roe"),
                "roa": item.get("roa"),
                "gross_margin": item.get("gross_margin"),
                "netprofit_margin": item.get("netprofit_margin"),
                "dividend_yield": item.get("dividend_yield"),
                "debt_to_assets": item.get("debt_to_assets"),
                "assets_to_eqt": item.get("assets_to_eqt"),
                "current_ratio": item.get("current_ratio"),
                "quick_ratio": item.get("quick_ratio"),
                "cash_ratio": item.get("cash_ratio"),
                "revenue_ttm": item.get("revenue_ttm"),
                "net_profit_ttm": item.get("net_profit_ttm"),
                "n_cashflow_act": item.get("n_cashflow_act"),
                "report_period": item.get("report_period"),
                "pct_change": item.get("pct_chg"),
                "reason": self._build_stock_reason(
                    item,
                    raw_conditions,
                    pe_display_field,
                    pe_display_label,
                    pb_display_field,
                    pb_display_label,
                    stability_checked,
                    stability_passed,
                ),
            })

        return stocks

    def _build_locked_result_reply(self, total_candidates: int, stocks: list[dict[str, Any]], batch_output: str) -> str:
        lines = ["The approved screening plan has been implemented."]
        if total_candidates:
            lines.append(f"共筛出 {total_candidates} 只候选。")

        batch_summary = next(
            (line.strip() for line in (batch_output or "").splitlines() if line.strip().startswith("📊 Summary:")),
            "",
        )
        if batch_summary:
            lines.append(batch_summary)

        if not stocks:
            if batch_output:
                lines.append("There were candidates in the original screening, but after verification of profitability stability, no final list was formed, and the threshold will no longer be relaxed.")
            else:
                lines.append("No final candidates have been formed to be displayed, and the threshold will no longer be relaxed.")
        else:
            if len(stocks) < 5:
                lines.append(f"当前仅有 {len(stocks)} 只候选满足条件，不再放宽阈值。")
            else:
                lines.append("The following are the 5 candidates that best meet the current conditions:")

            for index, stock in enumerate(stocks, 1):
                metrics = []
                if isinstance(stock.get("price"), (int, float)):
                    metrics.append(f"价格={stock['price']:.2f}元")
                if isinstance(stock.get("pe"), (int, float)):
                    metrics.append(f"{stock.get('pe_display_label') or 'PE'}={stock['pe']:.2f}")
                if isinstance(stock.get("pb"), (int, float)):
                    metrics.append(f"{stock.get('pb_display_label') or 'PB'}={stock['pb']:.2f}")
                if isinstance(stock.get("dividend_yield"), (int, float)):
                    metrics.append(f"股息率={stock['dividend_yield']:.2f}%")
                if isinstance(stock.get("roe"), (int, float)):
                    metrics.append(f"ROE={stock['roe']:.2f}%")

                header = f"{index}. {stock.get('code', '')} {stock.get('name', '')}"
                if stock.get("industry"):
                    header += f"（{stock['industry']}）"
                lines.append(header)
                if metrics:
                    lines.append(f"   - Key indicators:{'; '.join(metrics[:5])}")
                if stock.get("reason"):
                    lines.append(f"   - Reason:{stock['reason']}")

        lines.append("")
        lines.append("```json")
        lines.append(json.dumps({"stocks": stocks}, ensure_ascii=False, indent=2))
        lines.append("```")
        return "\n".join(lines)

    async def _invoke_tool_function(self, tool_name: str, **kwargs) -> str:
        func = (self._tool_functions or {}).get(tool_name)
        if not func:
            raise ValueError(f"Tool does not exist:{tool_name}")

        result = func(**kwargs)
        if inspect.isawaitable(result):
            result = await result
        return str(result or "")

    async def _run_locked_result_execution(
        self,
        message: str,
        locked_plan: dict,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> tuple[str, List[str], list[dict[str, Any]]]:
        """The tool is executed directly according to the approved planning parameters, and the final structured result is generated by the server."""
        tools_used: List[str] = []

        screen_args = locked_plan["screen"]
        raw_conditions = json.loads(screen_args.get("conditions_json", "[]"))
        await self._emit_progress(
            progress_callback,
            "status",
            phase="result",
            message="Run batch filters directly against approved execution plans",
        )
        screen_items, total_candidates = await _execute_screening_query(
            raw_conditions,
            int(screen_args.get("limit", 50)),
            screen_args.get("order_by_field", "total_mv"),
            screen_args.get("order_direction", "desc"),
        )
        screen_output = _format_screening_output(
            raw_conditions,
            screen_items,
            total_candidates,
            screen_args.get("order_by_field", "total_mv"),
        )
        tools_used.append("screen_stocks_by_criteria")

        batch_output = ""
        candidate_codes = [
            str(item.get("code") or item.get("symbol", "")).strip()
            for item in screen_items
            if str(item.get("code") or item.get("symbol", "")).strip()
        ]
        batch_plan = locked_plan.get("batch")
        if batch_plan and candidate_codes:
            batch_args = {
                "stock_codes_json": json.dumps(candidate_codes, ensure_ascii=False),
                "years": batch_plan.get("years", 3),
                "threshold_cv": batch_plan.get("threshold_cv", 0.3),
            }
            batch_output = await self._invoke_tool_function("batch_check_profit_consistency", **batch_args)
            tools_used.append("batch_check_profit_consistency")

        stocks = self._build_structured_stocks(
            screen_items,
            raw_conditions,
            screen_args.get("order_by_field", "total_mv"),
            batch_output,
        )
        reply = self._build_locked_result_reply(total_candidates, stocks, batch_output)
        return reply, tools_used, stocks

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: str,
        **data,
    ) -> None:
        """Send smart filtering progress events for WebSocket streaming display."""
        if not progress_callback:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data,
        }
        try:
            await progress_callback(payload)
        except Exception as e:
            logger.debug("[Smart filtering] Progress push failed(ignore): %s", e)

    def _build_conversation_title(self, message: str) -> str:
        text = re.sub(r"\s+", " ", (message or "").strip())
        if not text:
            return "未命名筛选"
        return text[:30]

    def _format_dt(self, value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None

    async def _ensure_conversation_doc_identity(self, doc: Optional[dict]) -> Optional[dict]:
        if not doc:
            return None

        messages = doc.get("messages") or []
        first_user_message = next(
            (item.get("content", "") for item in messages if item.get("role") == "user"),
            "",
        )
        updates: Dict[str, Any] = {}
        if not doc.get("conversation_id"):
            updates["conversation_id"] = uuid.uuid4().hex
        if not doc.get("title"):
            updates["title"] = self._build_conversation_title(first_user_message)

        if updates:
            await self._db.screening_conversations.update_one({"_id": doc["_id"]}, {"$set": updates})
            doc.update(updates)

        return doc

    async def _get_conversation_doc(self, user_id: str, conversation_id: Optional[str] = None) -> Optional[dict]:
        if conversation_id:
            doc = await self._db.screening_conversations.find_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return await self._ensure_conversation_doc_identity(doc)

        doc = await self._db.screening_conversations.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return await self._ensure_conversation_doc_identity(doc)

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        Core method: Processing user s stock selection request (three-stage process)

        stage 1 — Requirement confirmation (confirmation): LLM analyzes the requirements and returns understanding + Improvement suggestions without calling tools
        stage 2 — Execution planning (planning): LLM explains which tools to call and what parameters to use, but does not actually execute it.
        stage 3 — Execute screening (result): LLM calls the tool and returns 5 stocks
        """
        # 1. Get historical conversations
        resolved_conversation_id, history = await self._get_context_messages(user_id, conversation_id)
        if not resolved_conversation_id:
            resolved_conversation_id = conversation_id or uuid.uuid4().hex

        # 2. LLM Intent classification
        intent = await self._classify_intent(message, history)
        logger.info(f"[智能筛选] 用户={user_id} 意图分类={intent.get('intent')} 置信度={intent.get('confidence'):.2f}")

        # 3. First check whether it is a single stock query
        if intent.get("intent") == "single_stock_query":
            direct_result = await self._maybe_handle_single_stock_query(
                message,
                progress_callback=progress_callback,
            )
            if direct_result is not None:
                await self._save_message(
                    user_id,
                    resolved_conversation_id,
                    message,
                    direct_result["reply"],
                    direct_result.get("tools_used", []),
                    direct_result.get("stocks", []),
                    direct_result.get("phase", "result"),
                    is_fallback=False,
                )
                direct_result["conversation_id"] = resolved_conversation_id
                return direct_result

        if not await self._ensure_client():
            return {
                "reply": "Smart filtering is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings.",
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False,
            }

        set_current_user_id(user_id)

        # 4. Determine which stage you should enter now
        phase = self._determine_phase(history, message, intent)
        logger.info(f"[智能筛选] 用户={user_id} 当前阶段={phase} 消息={message[:50]}")
        await self._emit_progress(
            progress_callback,
            "phase_determined",
            phase=phase,
            message=(
                "正在分析您的筛选需求" if phase == "confirmation"
                else "正在生成筛选执行计划" if phase == "planning"
                else "正在执行批量筛选与验证"
            ),
        )

        # 5. Build message list (including history)
        # planning At this stage, the list of actually available tools needs to be passed into the prompt word to prevent LLM from hallucinating tool names.
        tool_summary = self._build_tool_summary(self._result_openai_tools) if phase == "planning" else ""
        system_prompt = self._get_system_prompt(phase, tool_summary, intent)
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        phase_history = self._select_phase_history(history, phase, message, intent)
        locked_plan = (
            self._extract_locked_execution_plan(phase_history)
            if phase == "result" and intent.get("intent") == "approval"
            else None
        )
        for h in phase_history:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        tools_used: List[str] = []
        structured_stocks: list = []

        async def _do_chat():
            nonlocal tools_used, structured_stocks
            if phase == "result":
                await self._emit_progress(
                    progress_callback,
                    "status",
                    phase=phase,
                    message="It has entered the execution stage and started to call the screening and stock watch list tools.",
                )
                if locked_plan:
                    logger.info("[Smart filtering] Directly execute the result phase using the approved plan")
                    content, locked_tools_used, locked_stocks = await self._run_locked_result_execution(
                        message,
                        locked_plan,
                        progress_callback=progress_callback,
                    )
                    tools_used.extend(locked_tools_used)
                    structured_stocks = locked_stocks
                    return content
                # Stage 3: Actual call to tool to perform filtering
                resp = await self._llm_client.achat(
                    messages,
                    tools=self._result_openai_tools,
                    auto_execute_tools=True,
                    max_tool_rounds=SCREENING_MAX_TOOL_ROUNDS,
                    tools_used=tools_used,
                    progress_callback=progress_callback,
                    log_payloads=True,
                    payload_log_label=f"intelligent_screening:{phase}",
                )
            else:
                await self._emit_progress(
                    progress_callback,
                    "status",
                    phase=phase,
                    message="正在生成阶段性回复",
                )
                # Phase 1 (confirmation) and phase 2 (planning): neither tool is called
                resp = await self._llm_client.achat(
                    messages,
                    tools=None,
                    log_payloads=True,
                    payload_log_label=f"intelligent_screening:{phase}",
                )
            return resp.content

        try:
            started_at = datetime.now(timezone.utc)
            content = await asyncio.wait_for(
                _do_chat(),
                timeout=SCREENING_RESULT_TIMEOUT_SECONDS if phase == "result" else ASSISTANT_TIMEOUT_SECONDS,
            )
            reply = content or "Sorry, the answer cannot be generated at the moment, please try again later."
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(
                f"[Smart filtering] Complete phase={phase} elapsed={elapsed:.2f}s tools_used={len(tools_used)}"
            )
            await self._emit_progress(
                progress_callback,
                "status",
                phase=phase,
                message=f"阶段处理完成，用时 {elapsed:.2f} 秒",
                tools_used=tools_used,
            )
        except asyncio.TimeoutError:
            timeout_seconds = (
                SCREENING_RESULT_TIMEOUT_SECONDS if phase == "result" else ASSISTANT_TIMEOUT_SECONDS
            )
            logger.warning(f"[智能筛选] 请求超时（{timeout_seconds}s，phase={phase}）")
            await self._emit_progress(
                progress_callback,
                "timeout",
                phase=phase,
                message=f"处理超时（{timeout_seconds} 秒）",
            )

            reply = self._build_timeout_reply(timeout_seconds)
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, [], "result")
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": [],
                "phase": "result",
                "conversation_id": resolved_conversation_id,
            }
        except Exception as e:
            logger.exception("[智能筛选] 对话失败")
            await self._emit_progress(
                progress_callback,
                "error",
                phase=phase,
                message=f"Processing failed:{str(e)}",
            )
            reply = f"An error occurred while processing your request:{str(e)}. Please try again later."
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, [], "result")
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": [],
                "phase": "result",
                "conversation_id": resolved_conversation_id,
            }

        # Extract stocks (result stage only)
        stocks = structured_stocks if phase == "result" and structured_stocks else self._extract_stocks(reply) if phase == "result" else []

        # Clean up JSON code block in reply (stock data has been returned via stocks field)
        if phase == "result":
            reply = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = re.sub(r'```\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = reply.strip()

        if phase == "result" and not stocks and "screen_stocks_by_criteria" in tools_used:
            reply = self._build_no_match_reply(message)
            stocks = []
            await self._emit_progress(
                progress_callback,
                "no_match",
                phase="result",
                message="No stocks matching the original filter criteria were found.",
                stocks=[],
            )
            await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, stocks, phase)
            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": stocks,
                "phase": phase,
                "conversation_id": resolved_conversation_id,
                "is_fallback": False,
            }

        await self._save_message(user_id, resolved_conversation_id, message, reply, tools_used, stocks, phase)
        return {
            "reply": reply,
            "tools_used": tools_used,
            "stocks": stocks,
            "phase": phase,
            "conversation_id": resolved_conversation_id,
            "is_fallback": False,
        }

    def _determine_phase(self, history: list, message: str, intent: Dict[str, Any] = None) -> str:
        """
        Determine which stage the current message should enter based on LLM intent classification

        Return 'confirmation' → Phase 1: LLM analyzes requirements without calling tools
        Return 'planning'     → Phase 2: LLM interprets the execution plan without calling tools
        Return 'result'       → Stage 3: LLM calls the tool and returns the stock list
        """
        # no history → new needs → Confirmation phase
        if not history:
            return "confirmation"

        # Find the most recent assistant message
        last_assistant = self._find_last_assistant(history)

        if not last_assistant:
            return "confirmation"

        last_phase = last_assistant.get("phase", "")
        intent_type = intent.get("intent") if intent else None

        if last_phase == "confirmation":
            # The user responded to the confirmation message → Entering the planning stage
            return "planning"

        if last_phase == "planning":
            # User responded to planning message
            if intent_type == "adjustment":
                # Users need to adjust their needs → Go back to the confirmation stage and re-understand
                return "confirmation"
            # Approval of plans or other → Entering the execution phase
            return "result"

        # last_phase == "result"
        if intent_type == "new_request":
            # Brand new stock selection needs → Reconfirm
            return "confirmation"

        # adjustment/approval/follow_up/single_stock_query → All are left in the result stage for processing.
        return "result"

    async def _get_context_messages(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[str, list]:
        """Get the latest N conversation history, which is used to pass to LLM as context"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc or not doc.get("messages"):
            return conversation_id or "", []
        messages = doc["messages"]
        return doc.get("conversation_id", conversation_id or ""), messages[-MAX_CONTEXT_MESSAGES:]

    def _build_tool_summary(self, tools: Optional[list] = None) -> str:
        """Convert the currently registered tool list into text descriptions for system prompts in the planning stage"""
        target_tools = tools if tools is not None else self._openai_tools
        if not target_tools:
            return "（暂无可用工具）"
        lines = []
        for t in target_tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            desc = fn.get("description", "")
            params = fn.get("parameters", {}).get("properties", {})
            param_names = ", ".join(params.keys()) if params else "无参数"
            lines.append(f"- `{name}`: {desc}\n  Parameters:{param_names}")
        return "\n".join(lines)

    def _get_system_prompt(self, phase: str, tool_summary: str = "", intent: Dict[str, Any] = None) -> str:
        """Construct system prompt words for stock picking experts (customized according to the stage)"""
        curr_date = _get_latest_trade_date()

        if phase == "confirmation":
            return f"""You are a professional A-share stock picking expert. Users have just put forward new stock selection requirements.

## Your task: Requirements analysis and confirmation

**Do not call any instruments and do not recommend stocks.** Please follow these steps to reply:

1. **Analyze and understand**: Refining the core conditions of user needs (industry, valuation, style, time dimension, etc.)
2. **show understanding**: Tell users in a clear list"I understand your need is..."
3. **Improvement suggestions**: Based on professional judgment, put forward 2-3 optional improvement suggestions (increase screening dimensions, adjust thresholds, supplementary considerations, etc.)
4. **Waiting for confirmation**: Explicitly ask the user whether"Filter by original requirements"Still"Filter after taking suggestions into consideration"

Additional rules:
- If the user uses low valuation  low PE  low PB This type of vague valuation description, but without a clear caliber, must explicitly point out this ambiguity during the confirmation stage.
- PE Relevant calibers should be distinguished `pe` (PE) and `pe_ttm` (PE(TTM)) 
- PB Relevant calibers should be distinguished `pb` (PB) and `pb_mrq` (PB(MRQ)) 
- When encountering such vague valuation requirements, you can first give a default recommended caliber, but the caliber must be clearly stated and the user must be prompted to confirm whether to adopt this caliber.

Reply format:
```
## 📋 needs analysis

I understand your stock selection needs are as follows:
- **Industry scope**: xxx
- **core conditions**: xxx
- **filter style**: xxx
- **Caliber to be confirmed**: If you mentioned Low PE/low PB/low valuation , I will further confirm using `pe` / `pe_ttm`, `pb` / `pb_mrq`

## 💡 Improvement suggestions

Based on professional analysis, I suggest you consider:
1. xxx (reason)
2. xxx (reason)
3. If low valuation It is a core requirement and it is recommended to adopt it explicitly. `pe_ttm` (PE(TTM)) Still `pe` (PE) , and adopt `pb_mrq` (PB(MRQ)) Still `pb` (PB) 

## ⏳ Please confirm

Please select:
- **Filter by original requirements** — Execute directly according to your conditions
- **Filter after taking suggestions** — Add the above improvement conditions before executing
```

Current date:{curr_date}
It only analyzes needs, does not recommend stocks, and does not use tools.
"""

        if phase == "planning":
            screening_fields_markdown = build_screening_fields_markdown(public_only=True)
            return f"""You are a professional A-share stock picking expert. The user has confirmed the stock selection needs, please formulate a detailed execution plan.

## List of available tools (strictly limited to the following tools, no other tool names may be used)

{tool_summary}

## `screen_stocks_by_criteria` Supported filter fields

{screening_fields_markdown}

Supported operators:> < >= <= == != between in not_in contains

**Note**: Fields such as audit_opinion_type (audit opinion type) and margin_of_safety_score (custom safety margin score) are not supported.
If user needs involve these conditions, please state in the plan that existing fields will be approximately replaced, or be honest about this restriction.

## Recommended two-step workflow

**The first step (wide-diameter batch screening)**: call `screen_stocks_by_criteria`, settings limit=50, According to hard indicators (PE(TTM)/PE, PB(MRQ)/PB, Market value, gearing ratio, is_st, etc.) to filter the candidate pool.
**Step Two (Profitability Stability Verification)**: Pass the list of candidate stock symbols to `batch_check_profit_consistency`, A query verifies the ROE stability in the past N years.**It is prohibited to repeatedly query financial data for each stock individually.**

## Field usage suggestions

- The valuation caliber must be written explicitly, not just in general terms. PE/PB : `pe` means PE,`pe_ttm` express PE(TTM), `pb` means PB,`pb_mrq` express PB(MRQ)
- If the user just says PE However, the caliber is not specified. Priority is given to specifying the fields you actually choose in the plan, for example Use `pe_ttm` (PE(TTM)) <= 15 or Use `pe` (PE) <= 15 
- If the user just says PB However, the caliber is not specified. Priority is given to specifying the fields you actually choose in the plan, for example Use `pb` (PB) <= 1.5 or Use `pb_mrq` (PB(MRQ)) <= 1.5 
- Prioritize using comparable ratio indicators for hard screening, such as PE(TTM)/PE, PB(MRQ)/PB, ROE, Gross profit margin, asset-liability ratio, current ratio, dividend rate
- `revenue_ttm`, `net_profit_ttm`, `n_cashflow_act` It is more suitable as a supplementary condition for quality and should not be used as the sole criterion alone.
- If the user emphasizes good cash flow  Solid profits  Financially sound , Prioritize `n_cashflow_act > 0`, `net_profit_ttm > 0`, `debt_to_assets`, `current_ratio`
- If the user emphasizes High dividends  Defensive , Prioritize `dividend_yield` and combine `debt_to_assets`, `n_cashflow_act`
- If the user emphasizes Latest financial report  Only view the latest financial reports , Passable `report_period` Add constraints

## Stock watch list linkage rules

- If the user explicitly requests After the screening is completed, add the stock to the watch list or Add last recommendation to stock watchlist , Can be called after the final recommendation is determined `add_stocks_to_favorites`
- If the user explicitly requests Tag/Tag/Tag  (Such as Tag Buffett ) , Priority call `add_stocks_to_favorites` and pass in `tags`
- If the user explicitly requests to be placed in a certain category/group (such as bank  To be analyzed ) , callable `add_stock_to_watchlist`, Use first when necessary `list_watchlist_groups` View existing categories
-  label and Group Not the same concept: tags written into stock watchlists `tags`, Group writing watchlist group
- Do not take the initiative to add stocks to your watch list if it is not explicitly proposed.

## Your Task: Execution Plan Description

**Do not call any instruments and do not recommend stocks.** Please describe in detail how you plan to perform this screening:

1. **Screening strategy**: Summarize the final filtering conditions and indicate which requirements can be supported by existing fields and which cannot be accurately filtered.
2. **Tool call plan**: **Only use tools from the list of available tools above**, List tool name and specific parameters
   - Step 1:`screen_stocks_by_criteria` JSON array of conditions (field/operator/value for each condition), limit suggestions 30-50
    - If a valuation field is used, the display caliber must be stated simultaneously in the text description, for example `pe_ttm` (PE(TTM))   `pb_mrq` (PB(MRQ))  
   - Step 2 (if you need to verify profitability stability):`batch_check_profit_consistency`, Pass in the candidate stock code list in step 1
3. **Data processing**: Explain how to select the final 5 stocks from the results returned by the tool (sort by, priority, etc.)
4. **Restrictions**: Honestly tell users which conditions cannot be accurately filtered (such as audit opinion types, customized safety margin scores)
5. **request approval**: Ask the user if they agree to the proposal

Reply format:
```
## 🔧 execution plan

### Filter criteria (final version)
- PE(TTM) < xxx (Use `pe_ttm` field)
- Market value > 50 billion (existing field support)
- Asset-liability ratio ≤ 60% (debt_to_assets field support)
- Non-ST shares (supported by is_st field)
- ROE stable in the past 3 years (batch_check_profit_consistency tool support)

### Tool call
**steps 1**: call `screen_stocks_by_criteria`
- conditions: [{{{{"field": "pe_ttm", "operator": "<", "value": 15}}}}, {{{{"field": "pb_mrq", "operator": "<=", "value": 1.5}}}}, {{{{"field": "total_mv", "operator": ">", "value": 50}}}}, {{{{"field": "is_st", "operator": "==", "value": false}}}}]
- limit: 50
- order_by_field: "pb_mrq"
- order_direction: "asc"

**steps 2**: call `batch_check_profit_consistency` (Verify the profitability stability of the candidate stocks in step 1 in batches)
- stock_codes_json: List of all stock symbols returned in step 1
- years: 3
- threshold_cv: 0.3

### Data processing
- Filter from step 2 results"Stable profits"stocks, press PB(MRQ) Take the first 5 in ascending order
- Make sure industries don t overlap

## ✅ Please confirm

The above is my execution plan, please choose:
- **Execute screening plan** — Execute this plan immediately
- **Re-describe requirements** — Re-adjust filters
```

Current date:{curr_date}
It only explains the plan, does not use tools, and does not recommend stocks.**It is strictly prohibited to use tool names other than those listed in the tool list.**
"""

        # phase == "result"
        intent_hint = ""
        if intent:
            intent_type = intent.get("intent")
            if intent_type == "adjustment":
                target = intent.get("adjustment_target")
                direction = intent.get("adjustment_direction")
                params = intent.get("explicit_parameters")
                intent_hint = f"""
## Current user intent analysis (important)

User wishes**Adjust filters**: 
- Adjust goals:{target or 'unknown indicator'}
- Adjust direction:{'relax conditions' if direction == 'loosen' else 'tighten conditions' if direction == 'tighten' else 'unknown'}
- Explicit parameters:{params or 'The user did not explicitly give a specific value, please infer based on the suggestions in the conversation history.'}

Please read the conversation history carefully to find the previous filtering conditions, then adjust them according to the user s intent and filter again.
Special note: If the assistant gives a specific adjustment suggestion form in the history (such as"relax ROE > 15% → ROE > 10%") , Please use that recommended value first.
"""
            elif intent_type == "approval":
                intent_hint = """
## Current user intent analysis (important)

The user has**Approve execution plan**, Please perform filtering immediately according to the previously planned parameters.
"""

        return f"""You are a professional A-share stock picking expert. The user has approved the execution plan, please execute the screening and recommend stocks immediately.
{intent_hint}
## Your task: Perform screening

1. **Call tool**: Called according to previously planned parameters `screen_stocks_by_criteria` Other tools to obtain data
2. **Featured recommendations**: Strictly recommended every time **5 only** The most eligible stocks
3. **Structured output**: Include the following JSON code block at the end of your answer

```json
{{{{
  "stocks": [
    {{{{
      "code": "600519",
      "name": "Kweichow Moutai",
      "industry": "Liquor",
      "price": 1680.00,
      "pe": 25.3,
    "pe_display_label": "PE",
      "pb": 8.5,
    "pb_display_label": "PB",
            "roe": 32.1,
            "roa": 18.6,
            "gross_margin": 51.2,
            "netprofit_margin": 24.8,
            "dividend_yield": 3.1,
            "debt_to_assets": 18.5,
            "assets_to_eqt": 1.42,
            "current_ratio": 4.2,
            "quick_ratio": 3.8,
            "cash_ratio": 1.9,
            "revenue_ttm": 123456789000,
            "net_profit_ttm": 45678900000,
            "n_cashflow_act": 39876500000,
            "report_period": "20250930",
      "pct_change": 2.1,
      "reason": "The leading white horse stock, with stable performance growth and valuation at the historical mid-range"
    }}}}
  ]
}}}}
```

## rules

- Current date:{curr_date}
- The default is to execute at most **Two rounds of data tool calls**: 
    - Round 1:`screen_stocks_by_criteria`
    - Round 2: Call only when absolutely necessary `batch_check_profit_consistency`
- If step 1 can directly select the final recommendation, then**skip**Step 2, directly output the final result
- Once enough data is available to generate final recommendations,**Stop calling tools immediately**
- Don t do it for Gather information Repeatedly change the threshold, repeat screening, or re-expand the scope; when the results under the current conditions are insufficient, the restrictions should be directly stated
- Recommend exactly 5 stocks each time, no more, no less
- Reasons for recommendations should be specific and combined with data.
- If ROE, dividend rate, asset-liability ratio, current ratio, and financial reporting period are already provided in the tool results, they should be put into the JSON field first to facilitate direct display on the front end.
- If ROA, gross profit margin, net profit margin, rolling revenue, rolling net profit, operating cash flow, equity multiplier, quick ratio, and cash ratio are already provided in the tool results, they can also be put into the JSON field to facilitate direct display on the front end.
- If the actual screening or display caliber is used `pe_ttm` / `pb_mrq`, The corresponding value must be written in `pe` / `pb` fields, and add them separately `pe_display_label` / `pb_display_label`, Strictly prohibited `PE(TTM)` written as `PE`, put `PB(MRQ)` written as `PB`
- If the user requests adjustments (e.g."Change industry""PE Lower") , Directly re-invoke the tool to adjust filtering
- If the user explicitly requests that the current recommendation result be added to the stock watch list, the user can call `add_stocks_to_favorites` One-time addition; if requested at the same time Tag/mark , pass tag `tags` Parameters are written together
- If the user explicitly requests to put the current recommendation results into a certain category/group, you can call `add_stock_to_watchlist`, Allows automatic creation of groups if they do not exist, e.g. bank  To be analyzed 
- If the user also requires Add to your choice + Tag + put into group , should be called first `add_stocks_to_favorites` Write tags and call again `add_stock_to_watchlist`
- Does not give specific buying/selling advice, only stock selection recommendations and analysis
- Only recommend A shares (Shanghai and Shenzhen Stock Exchanges)
"""

    def _extract_stocks(self, reply: str) -> list:
        """Extract structured stock list from LLM reply"""
        pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
        match = re.search(pattern, reply)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("stocks", [])
            except json.JSONDecodeError:
                pass
        return []

    async def _save_message(
        self, user_id: str, conversation_id: str, user_msg: str, assistant_reply: str,
        tools_used: List[str], stocks: list, phase: str, is_fallback: bool = False,
    ) -> None:
        """Persistent conversation messages arrive screening_conversations"""
        now = datetime.now(timezone.utc)
        user_entry = {"role": "user", "content": user_msg, "timestamp": now}
        assistant_entry = {
            "role": "assistant",
            "content": assistant_reply,
            "tools_used": tools_used,
            "stocks": stocks,
            "phase": phase,
            "is_fallback": is_fallback,
            "timestamp": now,
        }
        await self._db.screening_conversations.update_one(
            {"user_id": user_id, "conversation_id": conversation_id},
            {
                "$push": {
                    "messages": {
                        "$each": [user_entry, assistant_entry],
                        "$slice": -SCREENING_CONVERSATION_LIMIT,
                    }
                },
                "$set": {"updated_at": now},
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "title": self._build_conversation_title(user_msg),
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def run_direct_screening(
        self,
        user_id: str,
        criteria: str,
        max_stocks: int = 10,
    ) -> Dict[str, Any]:
        """
        Execute stock picking directly (single round, no confirmation/planning stage).
        For external calls such as MCP/API, without the need for multiple rounds of dialogue.

        Args:
            user_id: User ID (used for LLM quotas, etc.)
            criteria: Filter criteria (natural language) such as "PE Technology stocks less than 20"
            max_stocks: Maximum number of stocks returned, default 10

        Returns:
            {"reply": str, "stocks": list, "phase": "result"}
        """
        if not await self._ensure_client():
            return {
                "reply": "Smart filtering is temporarily unavailable, please check your LLM configuration.",
                "stocks": [],
                "phase": "result",
            }
        set_current_user_id(user_id)
        tools_used: List[str] = []

        async def _run_direct_flow() -> tuple[str, List[str], list]:
            planning_messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content=(
                        " [Direct execution mode] The user requires you to provide an executable stock selection plan within a single round."
                        "You are now only responsible for generating the tool execution plan in the planning phase. Do not call the tool or output the final stock recommendation."
                        f"The final limit on the number of stocks displayed is {max_stocks} Only.\n\n"
                        + self._get_system_prompt("planning", self._build_tool_summary(self._result_openai_tools))
                    ),
                ),
                Message(
                    role=MessageRole.USER,
                    content=f"Please directly generate a screening execution plan based on the following conditions without confirmation.\n\n Conditions:{criteria}",
                ),
            ]
            planning_response = await self._llm_client.achat(
                planning_messages,
                tools=None,
                log_payloads=True,
                payload_log_label="intelligent_screening:direct_planning",
            )
            planning_content = (planning_response.content if planning_response else None) or ""
            locked_plan = self._extract_locked_execution_plan([
                {"role": "assistant", "phase": "planning", "content": planning_content}
            ])
            if not locked_plan:
                raise ValueError("An executable filtering plan could not be parsed. Please add more specific filtering conditions and try again.")

            locked_plan["screen"]["limit"] = min(int(locked_plan["screen"].get("limit", max_stocks)), max_stocks)
            return await self._run_locked_result_execution(criteria, locked_plan)

        try:
            started_at = datetime.now(timezone.utc)
            reply, tools_used, stocks = await asyncio.wait_for(
                _run_direct_flow(),
                timeout=SCREENING_RESULT_TIMEOUT_SECONDS,
            )
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(f"[Smart filtering] run_direct_screening Complete elapsed={elapsed:.2f}s tools_used={len(tools_used)}")
        except asyncio.TimeoutError:
            reply = self._build_timeout_reply(SCREENING_RESULT_TIMEOUT_SECONDS)
            stocks = []
            tools_used = []
        except Exception as e:
            logger.exception("[Smart filtering] run_direct_screening failed")
            reply = f"An error occurred while processing the stock pick request:{str(e)}. Please try again later."
            stocks = []
        if not stocks and "screen_stocks_by_criteria" in tools_used:
            reply = self._build_no_match_reply(criteria)
            stocks = []

        return {"reply": reply, "stocks": stocks, "phase": "result", "is_fallback": False}

    async def get_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[Optional[str], list]:
        """获取完整对话历史"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc:
            return conversation_id, []
        return doc.get("conversation_id"), doc.get("messages", [])

    async def list_conversations(self, user_id: str) -> list:
        """获取会话列表摘要"""
        cursor = self._db.screening_conversations.find({"user_id": user_id}).sort([
            ("updated_at", -1),
            ("created_at", -1),
        ])
        docs = await cursor.to_list(length=100)

        items = []
        for raw_doc in docs:
            doc = await self._ensure_conversation_doc_identity(raw_doc)
            messages = doc.get("messages") or []
            preview = ""
            for item in reversed(messages):
                content = str(item.get("content") or "").strip()
                if content:
                    preview = re.sub(r"\s+", " ", content)[:80]
                    break

            items.append({
                "conversation_id": doc.get("conversation_id"),
                "title": doc.get("title") or self._build_conversation_title(preview),
                "preview": preview,
                "message_count": len(messages),
                "created_at": self._format_dt(doc.get("created_at")),
                "updated_at": self._format_dt(doc.get("updated_at")),
            })

        return items

    async def clear_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> None:
        """清空对话历史"""
        if conversation_id:
            await self._db.screening_conversations.delete_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return

        doc = await self._get_conversation_doc(user_id, None)
        if not doc:
            return
        await self._db.screening_conversations.delete_one({"_id": doc["_id"]})

