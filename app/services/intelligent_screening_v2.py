"""
Intelligent Screening Service V2 - Stock selection dialogue system based on intent understanding

Architecture design:
- Intent first: all decisions are based on LLM intent understanding, no hard-coded keywords
- State machine driver: clear dialogue state management
- End-to-end LLM coordination: LLM coordinates the entire process
"""

import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum

from motor.motor_asyncio import AsyncIOMotorDatabase

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

# Independent budget for stock selection scenarios
SCREENING_MAX_TOOL_ROUNDS = 3
SCREENING_RESULT_TIMEOUT_SECONDS = 300
MAX_CONTEXT_MESSAGES = 20
SCREENING_CONVERSATION_LIMIT = 50


async def _recall_user_plans_memory(db, user_id: str, query: str) -> str:
    """Recall the user s trading plan discipline/preference (user_preference) memory and inject it into the stock selection prompt.

    Reference:docs/05-design/v3.0/unified-memory-layer-mem0.md §15.5 P0-2
    """
    if not user_id:
        return ""
    try:
        from core.memory.service import get_memory_service
        svc = get_memory_service(db)
        return await svc.recall_formatted(
            query=query or "选股偏好",
            user_id=user_id,
            scopes=["user_preference", "trade_pattern"],
            limit=8,
            max_chars=900,
        )
    except Exception as e:
        logger.debug(f"[Smart filtering V2][mem0] Memory recall failed (ignored): {e}")
        return ""


def _build_plan_directive(memory_block: str) -> str:
    """Construct the Multiple Transaction Plan Processing Rules guidance fragment; return an empty string when memory_block is empty."""
    if not memory_block:
        return ""
    return (
        f"\n{memory_block}\n"
        " [Multiple trading plan processing rules] If there are multiple User s current trading plan: xxx (v number) entries in [Historical Memory]"
        " (For example, medium and long-term value , short-term band and flexible reserve ), indicating that users maintain multiple sets of coexisting strategies at the same time. Please follow the following rules for stock selection this time:\n"
        "1) Priority is given to whether the user s current round of news is clearly specified (such as stock selection based on medium and long-term plans and short-term opportunities ). If so, the corresponding planning discipline will be used.\n"
        "2) If it is not explicitly specified, but the demand is strongly correlated ( long-term holding tends to be mid- to long-term; short-term chasing tends to be short-term), select based on correlation and explain according to your xxx plan in the reply.\n"
        "3) When the style is not obvious, first ask the user Which plan do you want to choose stocks according to? (Medium and long term/short term/flexible)] , before continuing; don t default to the first one or mix multiple schedule disciplines.\n"
        "4) It is strictly prohibited to mix the stop loss/position/stock selection criteria of different plans.\n"
    )


class DialogState(Enum):
    """对话状态枚举"""
    IDLE = "idle"
    CONFIRMING = "confirming"
    PLANNING = "planning"
    EXECUTING = "executing"
    DONE = "done"


class IntentType(Enum):
    """意图类型枚举"""
    NEW_REQUEST = "new_request"
    ADJUST = "adjust"
    APPROVE = "approve"
    FOLLOW_UP = "follow_up"
    SINGLE_STOCK = "single_stock"


@dataclass
class IntentResult:
    """意图分类结果"""
    intent: IntentType
    slots: Dict[str, Any]
    confidence: float
    clarification_needed: bool
    clarification_question: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "intent": self.intent.value,
            "slots": self.slots,
            "confidence": self.confidence,
            "clarification_needed": self.clarification_needed,
            "clarification_question": self.clarification_question
        }


@dataclass
class ScreeningChatResponse:
    """智能筛选对话响应"""
    reply: str
    tools_used: List[str]
    stocks: List[dict]
    phase: str
    conversation_id: Optional[str] = None
    is_fallback: bool = False


class IntentClassifier:
    """纯LLM驱动的意图分类器"""

    def __init__(self, llm_client: UnifiedLLMClient):
        self.llm_client = llm_client

    async def classify(self, message: str, history: List[dict]) -> IntentResult:
        """
        Classify user intent and fill slots

        Args:
            message: Latest user news
            history: Conversation history

        Returns:
            IntentResult: Intent classification results
        """
        history_summary = self._build_history_summary(history)

        system_prompt = """You are a professional conversational intent classifier. Please analyze the user s latest news and combine it with the conversation history to determine the user s intention.

Return strict JSON format with no additional text:
{
    "intent": "new_request" | "adjust" | "approve" | "follow_up" | "single_stock",
    "slots": {
        "target_metric": "roe" | "pe" | "pb" | "margin" | "debt" | "cashflow" | "other" | null,
        "adjust_direction": "loosen" | "tighten" | null,
        "target_value": "10%" | "20" | "30%" | null,
        "stock_code": "002582" | "600519" | null,
        "stock_name": "miss you so much" | "Kweichow Moutai" | null,
        "action": "add_favorite" | "analyze" | null
    },
    "confidence": 0.95,
    "clarification_needed": false,
    "clarification_question": null
}

Intent definition:
- new_request: Users put forward new stock selection needs
- adjust: The user wants to adjust the previous filtering conditions (relax, tighten, modify, etc.)
- approve: The user explicitly approves a plan ("execute", "According to this plan", "OK", "OK", "Confirm", "yes", "No problem"etc.)
- follow_up: The user asks based on the current results ("How about these ones?", "Add to your choice", "Analyze it"etc.)
- single_stock: User asks about a single stock

Slot filling instructions:
- target_metric: When intent=adjust, indicate which indicator the user wants to adjust
- adjust_direction: When intent=adjust when it is pointed out that it is relaxing(loosen)Still tighten(tighten)
- target_value: Specific parameter values explicitly mentioned by the user
- stock_code/stock_name: When intent=single_stock Or extract when follow_up involves a single stock
- action: What the user wants to do

Clarification mechanism:
- Only set when the intent is very vague and it is completely impossible to tell what the user wants to do.clarification_needed=true
- **User reply"Confirm""yes""OK""OK"While waiting for the words of approval,intent=approve, clarification_needed=false**
- Don t because"Missing key parameters"While triggering clarification, missing parameters can be added in subsequent stages.

Example:
- Users say"Help me choose low-valuation bank stocks" → intent=new_request
- Users say"Let s relax ROE first" → intent=adjust, target_metric=roe, adjust_direction=loosen
- Users say"Change PE to<20" → intent=adjust, target_metric=pe, adjust_direction=loosen, target_value="20"
- Users say"Execute screening plan" → intent=approve
- Users say"Add these to your choice" → intent=follow_up, action=add_favorite
- Users say"How about Kweichow Moutai?" → intent=single_stock, stock_name="Kweichow Moutai"
"""

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(
                role=MessageRole.USER,
                content=f"Conversation history:\n{history_summary}\n\n Latest user news:{message}"
            )
        ]

        try:
            resp = await self.llm_client.achat(
                messages,
                tools=None,
                log_payloads=True,
                payload_log_label="intent_classification_v2"
            )
            content = resp.content if resp else ""
            result = self._parse_intent_result(content)
            return result
        except Exception as e:
            logger.warning(f"[Intent classification] LLM call failed: {e}")
            # Return default intent on failure
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )

    def _build_history_summary(self, history: List[dict]) -> str:
        """构建历史摘要"""
        if not history:
            return "无对话历史"

        recent = history[-6:]  # The last 6 items are enough to understand the context
        summary = []
        for h in recent:
            role = "用户" if h["role"] == "user" else "助手"
            content = h["content"][:300] + "..." if len(h["content"]) > 300 else h["content"]
            phase = h.get("phase", "")
            phase_tag = f" [{phase}]" if phase else ""
            summary.append(f"{role}{phase_tag}: {content}")

        return "\n".join(summary)

    def _parse_intent_result(self, content: str) -> IntentResult:
        """解析LLM返回的意图结果"""
        # Extract JSON
        json_match = re.search(r'\{[\s\S]*\}', content)
        if not json_match:
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )

        try:
            data = json.loads(json_match.group(0))
            intent_str = data.get("intent", "follow_up")
            intent = IntentType(intent_str) if intent_str in [t.value for t in IntentType] else IntentType.FOLLOW_UP

            return IntentResult(
                intent=intent,
                slots=data.get("slots", {}),
                confidence=float(data.get("confidence", 0.5)),
                clarification_needed=bool(data.get("clarification_needed", False)),
                clarification_question=data.get("clarification_question")
            )
        except Exception as e:
            logger.warning(f"[Intent classification] JSON Parsing failed: {e}")
            return IntentResult(
                intent=IntentType.FOLLOW_UP,
                slots={},
                confidence=0.5,
                clarification_needed=False
            )


class StateMachine:
    """对话状态机"""

    def __init__(self):
        pass

    def determine_state(self, history: List[dict], intent: IntentResult) -> DialogState:
        """
        Determine current state based on history and intent

        Args:
            history: Conversation history
            intent: Intent classification results

        Returns:
            DialogState: The current state that should be entered
        """
        if not history:
            return DialogState.CONFIRMING

        last_assistant = self._find_last_assistant(history)
        if not last_assistant:
            return DialogState.CONFIRMING

        last_phase = last_assistant.get("phase", "")

        # Decide based on final stage and intent
        if last_phase == "confirmation":
            return DialogState.PLANNING

        if last_phase == "planning":
            if intent.intent == IntentType.ADJUST:
                return DialogState.CONFIRMING
            return DialogState.EXECUTING

        # last_phase == "result" (That is DONE)
        if intent.intent == IntentType.NEW_REQUEST:
            return DialogState.CONFIRMING

        # Other situations are handled in the EXECUTING/DONE state
        return DialogState.EXECUTING

    def _find_last_assistant(self, history: List[dict]) -> Optional[dict]:
        """Find the last assistant message"""
        for msg in reversed(history):
            if msg.get("role") == "assistant":
                return msg
        return None


class IntelligentScreeningServiceV2:
    """
    Intelligent Screening Service V2 - Stock selection dialogue system based on intent understanding
    """

    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._openai_tools: Optional[list] = None
        self._result_openai_tools: Optional[list] = None
        self._tool_functions: Optional[dict] = None
        self._intent_classifier: Optional[IntentClassifier] = None
        self._state_machine = StateMachine()

    async def _ensure_client(self) -> bool:
        """Lazy loading of LLM clients and tools"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(self._db)
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
            self._intent_classifier = IntentClassifier(self._llm_client)
        except Exception as e:
            logger.error(f"[Smart filtering V2] Creating LLM client failed: {e}", exc_info=True)
            return False

        # Load stock picking related tools
        registry = get_tool_registry()
        all_metadata = registry.list_all()
        screening_metadata = [
            m for m in all_metadata
            if m.fc_enabled and (
                m.category in ["screening", "market", "fundamentals", "news", "china", "technical"]
                or m.id in ["add_stocks_to_favorites", "list_watchlist_groups", "add_stock_to_watchlist"]
            )
        ]
        self._openai_tools = tool_metadata_list_to_openai(screening_metadata)

        self._tool_functions = {}
        for tool in screening_metadata:
            func = registry.get_function(tool.id)
            if func:
                self._tool_functions[tool.id] = func

        # Only tools related to batch screening are retained in the results execution phase.
        self._result_openai_tools = self._filter_result_tools(self._openai_tools)
        if not self._result_openai_tools:
            self._result_openai_tools = self._openai_tools

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(f"[智能筛选V2] 已加载 {len(self._openai_tools)} 个选股工具")
        return True

    def _filter_result_tools(self, openai_tools: Optional[list]) -> list:
        """Available tools for filtering result stage"""
        if not openai_tools:
            return []

        allowlist = {"screen_stocks_by_criteria", "batch_check_profit_consistency",
                     "add_stocks_to_favorites", "list_watchlist_groups", "add_stock_to_watchlist"}
        filtered = []
        for t in openai_tools:
            fn = t.get("function", {}) if isinstance(t, dict) else {}
            name = fn.get("name")
            if name in allowlist:
                filtered.append(t)
        return filtered

    async def chat(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> Dict[str, Any]:
        """
        核心对话入口
        """
        # 1. Get historical conversations
        resolved_conversation_id, history = await self._get_context_messages(user_id, conversation_id)
        if not resolved_conversation_id:
            resolved_conversation_id = conversation_id or uuid.uuid4().hex

        # 2. Make sure the LLM client is ready
        if not await self._ensure_client():
            return self._error_response("Smart filtering is temporarily unavailable, please check LLM configuration", resolved_conversation_id)

        set_current_user_id(user_id)

        # 3. Intent classification
        intent = await self._intent_classifier.classify(message, history)
        logger.info(f"[智能筛选V2] 用户={user_id} 意图={intent.intent.value} 置信度={intent.confidence:.2f}")

        # 4. State machine judgment (first judge the status, and then decide whether clarification is needed)
        state = self._state_machine.determine_state(history, intent)
        logger.info(f"[Smart filtering V2] Current status={state.value}")

        # 5. Clarification is only allowed during the confirmation phase; users should not follow up while they are responding to a confirmation question
        if state == DialogState.CONFIRMING and intent.clarification_needed and intent.clarification_question:
            response = {
                "reply": intent.clarification_question,
                "tools_used": [],
                "stocks": [],
                "phase": "confirming",
                "conversation_id": resolved_conversation_id,
                "is_fallback": False
            }
            await self._save_message(user_id, resolved_conversation_id, message, response["reply"], [], [], "confirming")
            return response

        # 6. Route to corresponding processor
        response: Optional[Dict[str, Any]] = None

        if state == DialogState.CONFIRMING:
            response = await self._handle_confirming(user_id, message, history, intent, resolved_conversation_id, progress_callback)
        elif state == DialogState.PLANNING:
            response = await self._handle_planning(user_id, message, history, intent, resolved_conversation_id, progress_callback)
        elif state in [DialogState.EXECUTING, DialogState.DONE]:
            response = await self._handle_executing(user_id, message, history, intent, resolved_conversation_id, progress_callback)

        if response is None:
            response = self._error_response("Processing failed, please try again later", resolved_conversation_id)

        return response

    async def _handle_confirming(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理确认阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="confirmation", message="正在分析您的筛选需求")

        # Recall the user's trading plan/preference memory and inject it into prompt (multi-plan scenario)
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)

        system_prompt = self._get_confirmation_prompt() + plan_directive
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        try:
            resp = await asyncio.wait_for(
                self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="screening_confirmation"),
                timeout=ASSISTANT_TIMEOUT_SECONDS
            )
            reply = resp.content if resp else "Sorry, processing failed"

            await self._save_message(user_id, conversation_id, message, reply, [], [], "confirmation")

            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "confirmation",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            return self._error_response("Processing timeout, please try again later", conversation_id)
        except Exception as e:
            logger.exception("[确认阶段] 处理失败")
            return self._error_response(f"处理失败: {str(e)}", conversation_id)

    async def _handle_planning(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理规划阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="planning", message="正在生成筛选执行计划")

        tool_summary = self._build_tool_summary(self._result_openai_tools)
        # Recall trading plan/preference memory
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)
        system_prompt = self._get_planning_prompt(tool_summary) + plan_directive

        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        try:
            resp = await asyncio.wait_for(
                self._llm_client.achat(messages, tools=None, log_payloads=True, payload_log_label="screening_planning"),
                timeout=ASSISTANT_TIMEOUT_SECONDS
            )
            reply = resp.content if resp else "Sorry, processing failed"

            await self._save_message(user_id, conversation_id, message, reply, [], [], "planning")

            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "planning",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            return self._error_response("Processing timeout, please try again later", conversation_id)
        except Exception as e:
            logger.exception("[规划阶段] 处理失败")
            return self._error_response(f"处理失败: {str(e)}", conversation_id)

    async def _handle_executing(
        self,
        user_id: str,
        message: str,
        history: List[dict],
        intent: IntentResult,
        conversation_id: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> Dict[str, Any]:
        """处理执行阶段"""
        await self._emit_progress(progress_callback, "phase_determined", phase="result", message="正在执行批量筛选与验证")

        # First check if there is an approved plan that can be executed directly
        locked_plan = self._extract_locked_execution_plan(history) if intent.intent == IntentType.APPROVE else None

        # Recall trading plan/preference memory
        memory_block = await _recall_user_plans_memory(self._db, user_id, message)
        plan_directive = _build_plan_directive(memory_block)
        system_prompt = self._get_execution_prompt(intent, history) + plan_directive
        messages = [Message(role=MessageRole.SYSTEM, content=system_prompt)]
        for h in history[-MAX_CONTEXT_MESSAGES:]:
            role = MessageRole.USER if h["role"] == "user" else MessageRole.ASSISTANT
            messages.append(Message(role=role, content=h["content"]))
        messages.append(Message(role=MessageRole.USER, content=message))

        tools_used: List[str] = []
        structured_stocks: List[dict] = []

        async def _do_execute():
            nonlocal tools_used, structured_stocks

            if locked_plan:
                logger.info("[Smart filtering V2] Execute directly using approved plan")
                reply, locked_tools, locked_stocks = await self._run_locked_result_execution(
                    message, locked_plan, progress_callback
                )
                tools_used.extend(locked_tools)
                structured_stocks = locked_stocks
                return reply

            # Ordinary execution process
            resp = await self._llm_client.achat(
                messages,
                tools=self._result_openai_tools,
                auto_execute_tools=True,
                max_tool_rounds=SCREENING_MAX_TOOL_ROUNDS,
                tools_used=tools_used,
                progress_callback=progress_callback,
                log_payloads=True,
                payload_log_label="screening_execution"
            )
            return resp.content if resp else ""

        try:
            started_at = datetime.now(timezone.utc)
            reply = await asyncio.wait_for(_do_execute(), timeout=SCREENING_RESULT_TIMEOUT_SECONDS)
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            logger.info(f"[智能筛选V2] 执行完成 耗时={elapsed:.2f}s 工具={tools_used}")

            await self._emit_progress(progress_callback, "status", phase="result",
                                     message=f"阶段处理完成，用时 {elapsed:.2f} 秒", tools_used=tools_used)

            # Withdraw shares
            if not structured_stocks:
                structured_stocks = self._extract_stocks(reply)

            # Clean up JSON code block in reply (stock data has been returned via stocks field)
            reply = re.sub(r'```json\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = re.sub(r'```\s*\{[\s\S]*?\}\s*```', '', reply)
            reply = reply.strip()

            # If no stock is found and the filter tool is used, a clear no-result message is returned.
            if not structured_stocks and "screen_stocks_by_criteria" in tools_used:
                reply = self._build_no_match_reply(message)
                structured_stocks = []

            await self._save_message(user_id, conversation_id, message, reply, tools_used, structured_stocks, "result")

            return {
                "reply": reply,
                "tools_used": tools_used,
                "stocks": structured_stocks,
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except asyncio.TimeoutError:
            reply = self._build_timeout_reply(SCREENING_RESULT_TIMEOUT_SECONDS)
            await self._save_message(user_id, conversation_id, message, reply, [], [], "result")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }
        except Exception as e:
            logger.exception("[执行阶段] 处理失败")
            reply = f"处理您的请求时发生错误: {str(e)}。请稍后重试。"
            await self._save_message(user_id, conversation_id, message, reply, [], [], "result")
            return {
                "reply": reply,
                "tools_used": [],
                "stocks": [],
                "phase": "result",
                "conversation_id": conversation_id,
                "is_fallback": False
            }

    def _get_confirmation_prompt(self) -> str:
        """获取确认阶段提示词"""
        curr_date = _get_latest_trade_date()
        return f"""You are a professional A-share stock picking expert. Users have put forward stock selection or industry research needs.

## Your task: Requirements analysis and confirmation

**Do not call any instruments and do not recommend stocks.** Please follow these steps to reply:

1. **Analyze and understand**: Refining the core conditions of user needs (industry, valuation, style, time dimension, etc.)
2. **show understanding**: Tell users in a clear list"I understand your need is..."
3. **Improvement suggestions**: Based on professional judgment, make 2-3 optional suggestions for improvement.
4. **Waiting for confirmation**: Explicitly ask the user whether"Filter by original requirements"Still"Filter after taking suggestions into consideration"

## Important rules

- **Industry/sector issues**: Such as"What are the leaders in the pig industry?", should be understood as"Screen the leading companies in the industry sorted by market capitalization/revenue", Convert to filter criteria (industry=xxx + Descending order by market capitalization + Take the first N items),**Don t ask for specific stock names**
- **User reply"Confirm""OK""yes""OK"Wait**: Indicate approval of the current plan and do not ask further questions.
- If the user uses"low valuation"This type of vague description, but no clear caliber, please point out the ambiguity and suggest a default value
- PE Relevant caliber distinction PE / PE(TTM)
- PB Relevant caliber distinction PB / PB(MRQ)

Current date:{curr_date}
It only analyzes needs, does not recommend stocks, and does not use tools.
"""

    def _get_planning_prompt(self, tool_summary: str) -> str:
        """获取规划阶段提示词"""
        curr_date = _get_latest_trade_date()
        screening_fields = build_screening_fields_markdown(public_only=True)
        return f"""You are a professional A-share stock picking expert. The user has confirmed the stock selection needs, please formulate a detailed execution plan.

## List of available tools

{tool_summary}

## `screen_stocks_by_criteria` Supported filter fields

{screening_fields}

Supported operators:> < >= <= == != between in not_in contains

## Your Task: Execution Plan Description

**Do not call any instruments and do not recommend stocks.** Please describe in detail how you plan to perform this screening:

1. **Screening strategy**: Summarize the final filtering criteria used
2. **Tool call plan**: List the tool name and specific parameters (conditions in JSON format)
3. **Data processing**: Explain how to select the final 5 stocks from the results returned by the tool
4. **request approval**: Ask the user if they agree to the proposal

Please clearly include in your response format:
- `conditions`: [...]  (JSON array of filter conditions)
- `limit`: 50  (number of candidates)
- `order_by_field`: "total_mv"  (sort field)
- `order_direction`: "desc"  (Sorting direction)

Current date:{curr_date}
It only explains the plan, does not use tools, and does not recommend stocks.
"""

    def _get_execution_prompt(self, intent: IntentResult, history: List[dict]) -> str:
        """获取执行阶段提示词"""
        curr_date = _get_latest_trade_date()

        intent_hint = ""
        if intent.intent == IntentType.ADJUST:
            target = intent.slots.get("target_metric", "未知指标")
            direction = intent.slots.get("adjust_direction", "")
            params = intent.slots.get("target_value", "")
            intent_hint = f"""
## Current user intent analysis (important)

User wishes**Adjust filters**: 
- Adjust goals:{target}
- Adjust direction:{'relax conditions' if direction == 'loosen' else 'tighten conditions' if direction == 'tighten' else ''}
- Explicit parameters:{params or 'The user did not explicitly give a specific value, please infer based on the suggestions in the conversation history.'}

Please read the conversation history carefully to find the previous filtering conditions, then adjust them according to the user s intent and filter again.
Special note: If the assistant gives a specific adjustment suggestion form in the history (such as"relax ROE > 15% → ROE > 10%") , Please use that recommended value first.
"""
        elif intent.intent == IntentType.APPROVE:
            intent_hint = """
## Current user intent analysis (important)

The user has**Approve execution plan**, Please perform filtering immediately according to the previously planned parameters.
"""
        elif intent.intent == IntentType.FOLLOW_UP:
            action = intent.slots.get("action", "")
            if action == "add_favorite":
                intent_hint = """
## Current user intent analysis (important)

User wishes**Add filter results to watchlist**. Please:
1. call `add_stocks_to_favorites` Tool to add previously screened stocks to the user s watch list in batches
2. parameters `stocks_json` is a JSON array with the format of `[{"code":"002714","name":"Muyuan shares","market":"A shares"}]`
3. Passable `tags` Parameters label this batch of stocks (if the user specifies a group name, it can be used as a label)
4. Tell the user the results of the operation

**don t say"Unable to obtain group information"Or let the user operate manually, which must be completed by calling a tool.**
"""
            else:
                intent_hint = """
## Current user intent analysis (important)

User is in**Ask for current results**. Please use the appropriate tool to answer the user s question.
"""

        return f"""你是一位专业的 A 股选股专家。
{intent_hint}

## 你的任务

### 筛选任务
1. **调用工具**：按计划调用 `screen_stocks_by_criteria` 等工具获取数据
2. **精选推荐**：每次严格推荐 **5 只** 最符合条件的股票（如果筛选结果不足5只，就推荐实际找到的数量）
3. **结构化输出**：在回答最后包含以下 JSON 代码块

```json
{{
    "stocks": [
        {{
            "code": "002582",
            "name": "好想你",
            "industry": "食品",
            "price": 12.34,
            "pe": 2.78,
            "pe_display_label": "PE(TTM)",
            "pb": 1.05,
            "pb_display_label": "PB(MRQ)",
            "roe": 24.4,
            "dividend_yield": 8.11,
            "debt_to_assets": 32.0,
            "reason": "推荐理由..."
        }}
    ]
}}
```

### 关注列表操作
- 用户说"加入自选""加入关注"时，调用 `add_stocks_to_favorites` 批量添加到关注列表
- 参数 `stocks_json` 格式：`[{{"code":"002714","name":"牧原股份","market":"A股"}}]`
- 可通过 `tags` 参数给这批股票打标签
- **不要让用户手动操作，必须通过工具完成**

当前日期：{curr_date}
- 最多执行 {SCREENING_MAX_TOOL_ROUNDS} 轮工具调用
- 如果工具结果中没有足够数据，就直接说明，不要编造
- 不要给出具体的买入/卖出建议，只做选股推荐和分析
- 只推荐 A 股（沪深两市）
"""

    def _build_tool_summary(self, tools: Optional[list] = None) -> str:
        """构建工具摘要"""
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
            lines.append(f"- `{name}`: {desc}\n  参数: {param_names}")
        return "\n".join(lines)

    def _extract_locked_execution_plan(self, history: List[dict]) -> Optional[dict]:
        """Extract approved execution plans from history"""
        latest_planning = None
        for item in reversed(history):
            if item.get("role") == "assistant" and item.get("phase") == "planning":
                latest_planning = item
                break

        if not latest_planning:
            return None

        content = str(latest_planning.get("content", ""))
        conditions_match = re.search(r'`?conditions`?\s*[:：]\s*`(\[[\s\S]*?\])`', content)
        limit_match = re.search(r'`?limit`?\s*[:：]\s*(\d+)', content)
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

        return {
            "planning_content": content,
            "screen": {
                "conditions_json": json.dumps(raw_conditions, ensure_ascii=False),
                "limit": int(limit_match.group(1)) if limit_match else 50,
                "order_by_field": order_by_match.group(1) if order_by_match else "total_mv",
                "order_direction": order_direction_match.group(1) if order_direction_match else "desc",
            }
        }

    async def _run_locked_result_execution(
        self,
        message: str,
        locked_plan: dict,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]]
    ) -> tuple[str, List[str], List[dict]]:
        """按已批准计划直接执行"""
        tools_used: List[str] = []

        screen_args = locked_plan["screen"]
        raw_conditions = json.loads(screen_args.get("conditions_json", "[]"))

        await self._emit_progress(
            progress_callback, "status", phase="result", message="Run batch filters directly against approved execution plans"
        )

        screen_items, total_candidates = await _execute_screening_query(
            raw_conditions,
            int(screen_args.get("limit", 50)),
            screen_args.get("order_by_field", "total_mv"),
            screen_args.get("order_direction", "desc"),
        )
        tools_used.append("screen_stocks_by_criteria")

        stocks = self._build_structured_stocks(screen_items, raw_conditions, screen_args.get("order_by_field", "total_mv"), "")
        reply = self._build_locked_result_reply(total_candidates, stocks, "")

        return reply, tools_used, stocks

    def _build_structured_stocks(self, items: list, raw_conditions: list, order_by_field: str, batch_output: str) -> List[dict]:
        """构建结构化股票列表"""
        if not items:
            return []

        stocks: List[dict] = []
        for item in items[:5]:
            code = str(item.get("code") or item.get("symbol", "")).strip()
            if not code:
                continue

            pe_display_field, pe_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pe")
            pb_display_field, pb_display_label = select_metric_display_spec(raw_conditions, order_by_field, "pb")

            stocks.append({
                "code": code,
                "name": str(item.get("name", "")),
                "industry": str(item.get("industry", "")),
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
                "netprofit_ttm": item.get("net_profit_ttm"),
                "n_cashflow_act": item.get("n_cashflow_act"),
                "report_period": item.get("report_period"),
                "pct_change": item.get("pct_change"),
                "reason": "符合筛选条件"
            })
        return stocks

    def _build_locked_result_reply(self, total_candidates: int, stocks: List[dict], batch_output: str) -> str:
        """构建结果回复"""
        lines = ["The approved screening plan has been implemented."]
        if total_candidates:
            lines.append(f"共筛出 {total_candidates} 只候选。")

        if not stocks:
            lines.append("No matching stocks found.")
        else:
            lines.append(f"以下是最符合条件的 {len(stocks)} 只候选：")
            for i, stock in enumerate(stocks, 1):
                metrics = []
                if stock.get("price"):
                    metrics.append(f"价格={stock['price']:.2f}")
                if stock.get("pe"):
                    metrics.append(f"{stock.get('pe_display_label', 'PE')}={stock['pe']:.2f}")
                if stock.get("pb"):
                    metrics.append(f"{stock.get('pb_display_label', 'PB')}={stock['pb']:.2f}")
                if stock.get("roe"):
                    metrics.append(f"ROE={stock['roe']:.2f}%")

                lines.append(f"{i}. {stock.get('code')} {stock.get('name')} ({stock.get('industry', 'unknown')})")
                if metrics:
                    lines.append(f"   - {'; '.join(metrics)}")

        return "\n".join(lines)

    def _extract_stocks(self, reply: str) -> List[dict]:
        """从LLM回复中提取股票"""
        pattern = r'```json\s*(\{[\s\S]*?\})\s*```'
        match = re.search(pattern, reply)
        if match:
            try:
                data = json.loads(match.group(1))
                return data.get("stocks", [])
            except json.JSONDecodeError:
                pass
        return []

    def _build_no_match_reply(self, message: str) -> str:
        """构建无匹配结果的回复"""
        return f"No stocks matching the current filter criteria were found.\n\n There are currently no targets suitable for this screening requirement. If you still want to continue filtering, consider adjusting your criteria."

    def _build_timeout_reply(self, timeout_seconds: int) -> str:
        """构建超时回复"""
        return f"Sorry, processing your stock selection request has timed out (more than {timeout_seconds} seconds).\n\n Please narrow the filter scope, add more specific conditions, or try again later."

    def _error_response(self, message: str, conversation_id: str) -> Dict[str, Any]:
        """构建错误响应"""
        return {
            "reply": message,
            "tools_used": [],
            "stocks": [],
            "phase": "result",
            "conversation_id": conversation_id,
            "is_fallback": False
        }

    async def _emit_progress(
        self,
        progress_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]],
        event: str,
        **data
    ) -> None:
        """发送进度事件"""
        if not progress_callback:
            return

        payload = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **data
        }
        try:
            await progress_callback(payload)
        except Exception as e:
            logger.debug("[Smart filtering V2] Progress push failed: %s", e)

    async def _save_message(
        self,
        user_id: str,
        conversation_id: str,
        user_msg: str,
        assistant_reply: str,
        tools_used: List[str],
        stocks: List[dict],
        phase: str,
        is_fallback: bool = False
    ) -> None:
        """保存消息到数据库"""
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

    def _build_conversation_title(self, message: str) -> str:
        """构建会话标题"""
        text = re.sub(r"\s+", " ", (message or "").strip())
        if not text:
            return "未命名筛选"
        return text[:30]

    async def _get_context_messages(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[str, List[dict]]:
        """获取历史对话消息"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc or not doc.get("messages"):
            return conversation_id or "", []
        messages = doc["messages"]
        return doc.get("conversation_id", conversation_id or ""), messages[-MAX_CONTEXT_MESSAGES:]

    async def _get_conversation_doc(self, user_id: str, conversation_id: Optional[str] = None) -> Optional[dict]:
        """获取会话文档"""
        if conversation_id:
            doc = await self._db.screening_conversations.find_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return doc

        doc = await self._db.screening_conversations.find_one(
            {"user_id": user_id},
            sort=[("updated_at", -1), ("created_at", -1)],
        )
        return doc

    async def get_conversation(self, user_id: str, conversation_id: Optional[str] = None) -> tuple[Optional[str], List[dict]]:
        """获取完整对话历史"""
        doc = await self._get_conversation_doc(user_id, conversation_id)
        if not doc:
            return conversation_id, []
        return doc.get("conversation_id"), doc.get("messages", [])

    async def list_conversations(self, user_id: str) -> List[dict]:
        """获取会话列表"""
        cursor = self._db.screening_conversations.find({"user_id": user_id}).sort([
            ("updated_at", -1),
            ("created_at", -1),
        ])
        docs = await cursor.to_list(length=100)

        items = []
        for doc in docs:
            messages = doc.get("messages", [])
            preview = ""
            for item in reversed(messages):
                content = str(item.get("content", "")).strip()
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
        """清空会话"""
        if conversation_id:
            await self._db.screening_conversations.delete_one({
                "user_id": user_id,
                "conversation_id": conversation_id,
            })
            return

        doc = await self._get_conversation_doc(user_id, None)
        if doc:
            await self._db.screening_conversations.delete_one({"_id": doc["_id"]})

    def _format_dt(self, value: Any) -> Optional[str]:
        """格式化日期"""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return None
