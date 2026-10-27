"""
Planning analysis services — Plan-then-Execute mode

Arrange three-level assurance process:
  1. Seed process matching → 2. LLM independent planning → 3. ReAct rollback

Dependency sharing layer (from intelligent_assistant_service):
  - _get_assistant_llm_config()
  - _get_system_prompt()
  - _get_latest_trade_date()
"""

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncGenerator, AsyncIterator, Dict, List, Optional

from core.agents.plan_executor import PlanExecutor
from core.agents.planner import Planner
from core.agents.planner_models import (
    AnalysisPlan,
    PlanSource,
    PlanStep,
    PlannedAnalysisResult,
    StepResult,
    SupplementRequest,
)
from core.llm import UnifiedLLMClient
from core.llm.models import Message, MessageRole
from core.tools import get_tool_registry, tool_metadata_list_to_openai

from app.services.intelligent_assistant_service import (
    _get_assistant_llm_config,
    _build_assistant_model_preferences,
    _build_fallback_memory_facts,
    _get_preferred_assistant_config_id,
    _get_preferred_assistant_model,
    _get_system_prompt,
    _get_latest_trade_date,
    get_assistant_conversation,
    get_or_create_assistant_thread,
    IntelligentAssistantService,
    save_assistant_message,
)

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _store_planned_analysis_memory(
    db,
    user_id: str,
    conversation_id: str,
    user_message: str,
    reply: str,
    tools_used: List[str],
    source: str,
) -> None:
    """Planning analysis replies are no longer written to mem0 long-term memory to avoid free text pollution."""
    return


# ============================================================
# Does not support variety detection
# ============================================================
# The vocabulary list and detection logic have been integrated into core.assistant.lexicon (A11 Phase 4: Dictionary Convergence Unit,
# Assistant routing and planning analysis share the same set of variety gates), and only compatible commissions are retained here.


def _check_unsupported_asset(question: str) -> Optional[str]:
    """Detect if the user question involves an unsupported symbol type (source of fact: core.assistant.lexicon).

    Returns:
        If an unsupported variety is detected, a prompt message is returned; otherwise, None is returned.
    """
    from core.assistant.lexicon import detect_unsupported_asset
    return detect_unsupported_asset(question)

# overall timeout
PLANNED_ANALYSIS_TIMEOUT = int(os.environ.get("PLANNED_ANALYSIS_TIMEOUT", "180"))

# Maximum number of session contexts
MAX_CONTEXT_MESSAGES = 5


def _build_synthesize_prompt(
    question: str,
    plan: AnalysisPlan,
    step_results: List[StepResult],
) -> str:
    """build synthesis phase prompt"""
    results_text = ""
    for sr in step_results:
        status = "✅ 成功" if sr.success else f"❌ 失败: {sr.error}"
        result_preview = str(sr.result)[:2000] if sr.result else "(无数据)"
        results_text += f"\n### 步骤 {sr.step_id}: {sr.intent}\n"
        results_text += f"- 工具: {sr.tool}\n- 状态: {status}\n"
        results_text += f"- data:\n```\n{result_preview}\n```\n"

    return f"""基于以下分析数据，回答用户问题。

## 用户问题
{question}

## 分析结果
{results_text}

## 要求（以投资教练的身份回答）
1. 基于工具返回的客观数据进行解读，教用户如何理解这些数据
2. 讲解分析方法和框架，引导用户建立自己的判断，不给"买入/卖出"的直接建议
3. 遇到专业概念时用通俗语言解释
4. 如果某些数据获取失败，说明原因并基于已有数据回答
5. 如果数据严重不足无法回答，在回答末尾添加一行: [NEED_SUPPLEMENT]
6. 使用 Markdown 格式，条理清晰
7. 结尾自然提醒：以上分析仅供学习参考，不构成投资建议

请回答："""


def _build_supplement_prompt(
    question: str,
    current_answer: str,
) -> str:
    """Build supplementary request judgment prompt"""
    return f"""你之前基于工具数据回答了用户问题，但标记了数据不足。

## 用户问题
{question}

## 当前回答（不完整）
{current_answer}

## 要求
如果需要补充数据，返回 JSON 格式的补充请求：
```json
{{
  "reason": "需要补充的原因",
  "steps": [
    {{"id": 1, "tool": "工具ID", "args": {{"参数": "值"}}, "intent": "目的", "depends_on": []}}
  ]
}}
```
补充步骤最多 2 个。如果不需要补充直接返回 "none"。"""


class PlannedAnalysisService:
    """
    Planning analysis services

    Completely arranged Plan → Execute → Synthesize process.
    If planning fails, fall back to ReAct mode (reuse IntelligentAssistantService).
    """

    def __init__(self, db, preferred_models: Optional[Dict[str, Any]] = None):
        self._db = db
        self._llm_client: Optional[UnifiedLLMClient] = None
        self._tool_functions: Optional[Dict[str, Any]] = None
        self._openai_tools: Optional[List[Dict[str, Any]]] = None
        self._preferred_model = _get_preferred_assistant_model(preferred_models)
        self._preferred_model_config_id = _get_preferred_assistant_config_id(preferred_models)

    def _get_react_preferred_models(self) -> Dict[str, str]:
        if not self._preferred_model and not self._preferred_model_config_id:
            return {}
        preferred: Dict[str, str] = {}
        if self._preferred_model:
            preferred["model"] = self._preferred_model
        if self._preferred_model_config_id:
            preferred["model_config_id"] = self._preferred_model_config_id
        return preferred

    async def _ensure_client(self) -> bool:
        """Make sure the LLM client and tools are loaded"""
        if self._llm_client is not None:
            return True

        llm_config = await _get_assistant_llm_config(
            self._db,
            preferred_models=self._get_react_preferred_models() or None,
        )
        if not llm_config:
            return False

        try:
            self._llm_client = UnifiedLLMClient.from_config(llm_config)
        except Exception as e:
            logger.error(f"[planning analysis] Creating LLM client failed: {e}", exc_info=True)
            return False

        registry = get_tool_registry()
        all_metadata = registry.list_all()
        self._openai_tools = tool_metadata_list_to_openai(all_metadata)

        self._tool_functions = {}
        for tool in all_metadata:
            if tool.fc_enabled and tool.parameters:
                func = registry.get_function(tool.id)
                if func:
                    self._tool_functions[tool.id] = func

        self._llm_client.inject_tools(self._tool_functions)
        logger.info(f"[规划分析] 已加载 {len(self._openai_tools)} 个工具")
        return True

    # ----------------------------------------------------------
    # public interface
    # ----------------------------------------------------------

    async def analyze(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """
        Perform planning analysis.

        Args:
            question: User issues
            user_id: User ID (used to get session history)
            conversation_id: session ID

        Returns:
            PlannedAnalysisResult
        """
        # === Pre-check: Unsupported symbol type ===
        unsupported_msg = _check_unsupported_asset(question)
        if unsupported_msg:
            logger.info(f"[planning analysis] If an unsupported variety type is detected, a prompt will be returned directly.")
            return PlannedAnalysisResult(
                reply=unsupported_msg,
                source=PlanSource.SEED_FLOW,
            )

        if not await self._ensure_client():
            return PlannedAnalysisResult(
                reply="Intelligent analysis is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings.",
                source=PlanSource.REACT_FALLBACK,
            )

        try:
            return await asyncio.wait_for(
                self._do_analyze(question, user_id, conversation_id),
                timeout=PLANNED_ANALYSIS_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[规划分析] 整体超时（{PLANNED_ANALYSIS_TIMEOUT}s）")
            return PlannedAnalysisResult(
                reply=f"Sorry, the analysis took too long (exceeded {PLANNED_ANALYSIS_TIMEOUT} seconds).\n\n"
                      "We recommend that you try breaking the question into more specific details or try again later.",
                source=PlanSource.REACT_FALLBACK,
            )
        except Exception as e:
            logger.exception("[规划分析] 分析失败")
            return PlannedAnalysisResult(
                reply=f"An error occurred while processing your request:{str(e)}. Please check the network and LLM configuration and try again.",
                source=PlanSource.REACT_FALLBACK,
            )

    async def analyze_stream(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Streaming execution planning analysis and output SSE events."""
        unsupported_msg = _check_unsupported_asset(question)
        if unsupported_msg:
            yield _sse("token", {"content": unsupported_msg})
            yield _sse(
                "done",
                {
                    "reply": unsupported_msg,
                    "tools_used": [],
                    "source": PlanSource.SEED_FLOW.value,
                    "supplemented": False,
                },
            )
            return

        if not await self._ensure_client():
            message = "Intelligent analysis is temporarily unavailable, please check whether the LLM configuration has been configured correctly in Settings."
            yield _sse("token", {"content": message})
            yield _sse(
                "done",
                {
                    "reply": message,
                    "tools_used": [],
                    "source": PlanSource.REACT_FALLBACK.value,
                    "supplemented": False,
                },
            )
            return

        tools_used: List[str] = []
        collected_step_results: List[StepResult] = []
        supplemented = False
        plan: Optional[AnalysisPlan] = None

        try:
            context_messages = await self._get_context_messages(user_id, conversation_id)

            curr_date = _get_latest_trade_date()
            trade_date = curr_date

            knowledge_snippets = ""
            try:
                from core.knowledge import FinancialKnowledgeManager
                km = FinancialKnowledgeManager(db=self._db)
                knowledge_snippets = km.retrieve_for_prompt(question)
            except Exception as e:
                logger.debug(f"[planning analysis] Knowledge retrieval skip: {e}")

            yield _sse("plan_started", {"message": "正在规划分析步骤"})

            planner = Planner(
                llm_client=self._llm_client,
                curr_date=curr_date,
                trade_date=trade_date,
            )
            plan = await planner.plan(question, context_messages, knowledge_snippets=knowledge_snippets)

            if plan.source == PlanSource.REACT_FALLBACK:
                yield _sse(
                    "mode_switch",
                    {"source": PlanSource.REACT_FALLBACK.value, "message": "Planning fails and falls back to ReAct mode"},
                )
                react_service = IntelligentAssistantService(
                    self._db,
                    preferred_models=self._get_react_preferred_models(),
                )
                async for event_str in react_service.chat_stream(question, conversation_id):
                    yield event_str
                return

            yield _sse(
                "plan_ready",
                {
                    "plan": plan.model_dump(),
                    "source": plan.source.value,
                },
            )

            executor = PlanExecutor()
            step_queue: asyncio.Queue = asyncio.Queue()

            def _on_step_started(step_id: int, tool: str, intent: str):
                step_queue.put_nowait(
                    {
                        "event": "step_started",
                        "step_id": step_id,
                        "tool": tool,
                        "intent": intent,
                    }
                )

            def _on_step_completed(sr: StepResult):
                tools_used.append(sr.tool)
                step_queue.put_nowait(
                    {
                        "event": "step_completed",
                        "step_result": sr.model_dump(),
                    }
                )

            execute_task = asyncio.create_task(
                executor.execute(
                    plan,
                    on_step_started=_on_step_started,
                    on_step_completed=_on_step_completed,
                )
            )

            while not execute_task.done() or not step_queue.empty():
                try:
                    payload = await asyncio.wait_for(step_queue.get(), timeout=0.3)
                    event_name = payload.pop("event", "progress")
                    if event_name == "step_completed":
                        step_result = payload.get("step_result")
                        if step_result:
                            collected_step_results.append(StepResult(**step_result))
                    yield _sse(event_name, payload)
                except asyncio.TimeoutError:
                    continue

            step_results = await execute_task
            collected_step_results = step_results

            yield _sse("synthesis_started", {"message": "正在汇总结论并生成报告"})
            reply_parts: List[str] = []
            async for chunk in self._stream_synthesize_chunks(question, plan, collected_step_results):
                reply_parts.append(chunk)
                yield _sse("token", {"content": chunk})
            reply = "".join(reply_parts)

            if "[NEED_SUPPLEMENT]" in reply:
                reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
                yield _sse("supplement_started", {"message": "正在补充缺失数据"})
                supplement_result = await self._try_supplement(question, reply, plan, tools_used)
                if supplement_result:
                    for sr in supplement_result:
                        collected_step_results.append(sr)
                        yield _sse("step_completed", {"step_result": sr.model_dump()})

                    yield _sse("synthesis_started", {"message": "Supplement completed, answers are being rearranged"})
                    reply_parts = []
                    async for chunk in self._stream_synthesize_chunks(question, plan, collected_step_results):
                        reply_parts.append(chunk)
                        yield _sse("token", {"content": chunk})
                    reply = "".join(reply_parts).replace("[NEED_SUPPLEMENT]", "").strip()
                    supplemented = True

            yield _sse(
                "done",
                {
                    "reply": reply,
                    "tools_used": list(set(tools_used)),
                    "step_results": [sr.model_dump() for sr in collected_step_results],
                    "plan": plan.model_dump() if plan else None,
                    "source": plan.source.value if plan else PlanSource.LLM_PLAN.value,
                    "supplemented": supplemented,
                },
            )
        except asyncio.CancelledError:
            yield _sse("error", {"message": "请求已取消"})
            yield _sse("done", {"tools_used": list(set(tools_used)), "error": True})
        except Exception as e:
            logger.exception("[planning analysis] Streaming analysis failed")
            yield _sse("error", {"message": f"An error occurred while processing the request:{str(e)}"})
            yield _sse("done", {"tools_used": list(set(tools_used)), "error": True})

    # ----------------------------------------------------------
    # internal implementation
    # ----------------------------------------------------------

    async def _do_analyze(
        self,
        question: str,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """核心分析流程"""
        # Get session context
        context_messages = await self._get_context_messages(user_id, conversation_id)

        curr_date = _get_latest_trade_date()
        trade_date = curr_date  # The trading day is consistent with the current date (_get_latest_trade_date handles weekends)

        # RAG Dynamic knowledge retrieval (graceful degradation: returns empty string when unavailable)
        knowledge_snippets = ""
        try:
            from core.knowledge import FinancialKnowledgeManager
            km = FinancialKnowledgeManager(db=self._db)
            knowledge_snippets = km.retrieve_for_prompt(question)
        except Exception as e:
            logger.debug(f"[planning analysis] Knowledge retrieval skip: {e}")

        # === Phase 1: Planning ===
        planner = Planner(
            llm_client=self._llm_client,
            curr_date=curr_date,
            trade_date=trade_date,
        )
        plan = await planner.plan(question, context_messages, knowledge_snippets=knowledge_snippets)

        # Third level fallback:ReAct
        if plan.source == PlanSource.REACT_FALLBACK:
            return await self._react_fallback(question, conversation_id)

        # === Phase 2: Execution ===
        tools_used: List[str] = []
        executor = PlanExecutor()
        step_results = await executor.execute(
            plan,
            on_step_started=lambda sid, tool, intent: logger.info(
                f"[规划分析] 步骤 {sid} 开始: {tool} - {intent}"
            ),
            on_step_completed=lambda sr: (
                tools_used.append(sr.tool),
                logger.info(
                    f"[规划分析] 步骤 {sr.step_id} 完成: "
                    f"{'success' if sr.success else 'failed'} ({sr.duration_ms}ms)"
                ),
            ),
        )

        # === Stage 3: Synthesis ===
        reply = await self._synthesize(question, plan, step_results)

        # Limited replenishment mechanism
        supplemented = False
        if "[NEED_SUPPLEMENT]" in reply:
            reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
            supplement_result = await self._try_supplement(
                question, reply, plan, tools_used
            )
            if supplement_result:
                step_results.extend(supplement_result)
                reply = await self._synthesize(question, plan, step_results)
                reply = reply.replace("[NEED_SUPPLEMENT]", "").strip()
                supplemented = True

        return PlannedAnalysisResult(
            reply=reply,
            plan=plan,
            tools_used=list(set(tools_used)),
            step_results=step_results,
            source=plan.source,
            supplemented=supplemented,
        )

    async def _synthesize(
        self,
        question: str,
        plan: AnalysisPlan,
        step_results: List[StepResult],
    ) -> str:
        """Synthesis phase: generating the final answer based on the results of the steps"""
        system_prompt = _get_system_prompt()
        synth_prompt = _build_synthesize_prompt(question, plan, step_results)

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=synth_prompt),
        ]

        try:
            resp = await self._llm_client.achat(messages)
            return resp.content or "Sorry, we are unable to generate a comprehensive analysis at this time."
        except Exception as e:
            logger.error(f"[planning analysis] Synthesis phase failed: {e}")
            # Downgrade: splicing raw data
            parts = [f"## {question}\n"]
            for sr in step_results:
                if sr.success and sr.result:
                    parts.append(f"### {sr.intent}\n{str(sr.result)[:1000]}\n")
            parts.append("\n> ⚠️ Comprehensive analysis failed to generate. The above is a summary of the original data.")
            return "\n".join(parts)

    async def _stream_synthesize_chunks(
        self,
        question: str,
        plan: AnalysisPlan,
        step_results: List[StepResult],
    ) -> AsyncIterator[str]:
        """The synthesis stage streams the token."""
        system_prompt = _get_system_prompt()
        synth_prompt = _build_synthesize_prompt(question, plan, step_results)

        messages = [
            Message(role=MessageRole.SYSTEM, content=system_prompt),
            Message(role=MessageRole.USER, content=synth_prompt),
        ]

        try:
            has_chunk = False
            async for chunk in self._llm_client.astream(messages):
                if chunk:
                    has_chunk = True
                    yield chunk
            if not has_chunk:
                fallback = await self._synthesize(question, plan, step_results)
                for i in range(0, len(fallback), 120):
                    yield fallback[i:i + 120]
        except Exception as e:
            logger.warning(f"[planning analysis] Synthetic streaming output fails, falling back to non-streaming synthesis: {e}")
            fallback = await self._synthesize(question, plan, step_results)
            for i in range(0, len(fallback), 120):
                yield fallback[i:i + 120]

    async def _try_supplement(
        self,
        question: str,
        current_answer: str,
        plan: AnalysisPlan,
        tools_used: List[str],
    ) -> Optional[List[StepResult]]:
        """Limited replenishment mechanic: max 1 round, max 2 tool calls"""
        prompt = _build_supplement_prompt(question, current_answer)
        messages = [
            Message(role=MessageRole.SYSTEM, content="You are a stock analysis planner that only outputs JSON or none."),
            Message(role=MessageRole.USER, content=prompt),
        ]

        try:
            resp = await self._llm_client.achat(messages)
            raw = (resp.content or "").strip()

            if raw.lower() == "none" or not raw:
                return None

            # Parse supplementary requests
            import re
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            text = json_match.group(1).strip() if json_match else raw.strip()
            start = text.find("{")
            end = text.rfind("}")
            if start == -1 or end == -1:
                return None

            data = json.loads(text[start:end + 1])
            raw_steps = data.get("steps", [])[:2]  # Up to 2

            # Build the supplementary steps and execute
            supplement_steps = []
            max_id = max((s.id for s in plan.steps), default=0)
            for i, s in enumerate(raw_steps):
                supplement_steps.append(PlanStep(
                    id=max_id + i + 1,
                    tool=s.get("tool", ""),
                    args=s.get("args", {}),
                    intent=s.get("intent", "补充数据"),
                    depends_on=[],
                ))

            if not supplement_steps:
                return None

            logger.info(f"[规划分析] 执行补充调用: {len(supplement_steps)} 个步骤")
            supplement_plan = AnalysisPlan(
                question=question,
                steps=supplement_steps,
            )
            executor = PlanExecutor()
            results = await executor.execute(
                supplement_plan,
                on_step_completed=lambda sr: tools_used.append(sr.tool),
            )
            return results

        except Exception as e:
            logger.warning(f"[planning analysis] Supplementary call failed: {e}")
            return None

    async def _react_fallback(
        self,
        question: str,
        conversation_id: Optional[str] = None,
    ) -> PlannedAnalysisResult:
        """Third level fallback: Use existing ReAct mode"""
        logger.info("[planning analysis] Fallback to ReAct mode")
        react_service = IntelligentAssistantService(
            self._db,
            preferred_models=self._get_react_preferred_models(),
        )
        result = await react_service.chat(question, conversation_id)
        return PlannedAnalysisResult(
            reply=result.get("reply", ""),
            tools_used=result.get("tools_used", []),
            source=PlanSource.REACT_FALLBACK,
        )

    async def _get_context_messages(
        self,
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
    ) -> Optional[List[Message]]:
        """Get recent session history as context"""
        if not user_id:
            return None

        try:
            raw_messages = await get_assistant_conversation(
                self._db,
                user_id,
                conversation_id,
            )
            if not raw_messages:
                return None

            recent = raw_messages[-MAX_CONTEXT_MESSAGES:]
            messages = []
            for m in recent:
                role = MessageRole.USER if m["role"] == "user" else MessageRole.ASSISTANT
                content = m.get("content", "")
                if content:
                    # Truncate too long historical messages
                    messages.append(Message(
                        role=role,
                        content=content[:500],
                    ))
            return messages if messages else None

        except Exception as e:
            logger.warning(f"[planning analysis] Failed to get session history: {e}")
            return None


async def stream_planned_analysis_with_assistant(
    db,
    user_message: str,
    user_id: str,
    conversation_id: Optional[str] = None,
    model: Optional[str] = None,
    model_config_id: Optional[str] = None,
    quick_model: Optional[str] = None,
    quick_model_config_id: Optional[str] = None,
    deep_model: Optional[str] = None,
    deep_model_config_id: Optional[str] = None,
) -> AsyncGenerator[str, None]:
    """Provides external planning and analysis streaming interface with persistence."""
    service = PlannedAnalysisService(
        db,
        preferred_models=_build_assistant_model_preferences(
            model=model,
            model_config_id=model_config_id,
            quick_model=quick_model,
            quick_model_config_id=quick_model_config_id,
            deep_model=deep_model,
            deep_model_config_id=deep_model_config_id,
        ),
    )

    collected_reply = ""
    collected_tools: List[str] = []
    collected_plan: Optional[Dict[str, Any]] = None
    collected_step_results: List[Dict[str, Any]] = []
    source = PlanSource.LLM_PLAN.value
    supplemented = False

    async for event_str in service.analyze_stream(
        question=user_message.strip(),
        user_id=user_id,
        conversation_id=conversation_id,
    ):
        if event_str.startswith("event: done\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                collected_tools = data.get("tools_used", [])
                collected_reply = data.get("reply", collected_reply)
                collected_plan = data.get("plan")
                collected_step_results = data.get("step_results", [])
                source = data.get("source", source)
                supplemented = data.get("supplemented", supplemented)
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
        elif event_str.startswith("event: plan_ready\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                collected_plan = data.get("plan")
                source = data.get("source", source)
            except Exception:
                pass
        elif event_str.startswith("event: mode_switch\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                source = data.get("source", source)
            except Exception:
                pass
        elif event_str.startswith("event: step_completed\n"):
            try:
                data_line = event_str.split("\ndata: ", 1)[1].rstrip("\n")
                data = json.loads(data_line)
                step_result = data.get("step_result")
                if step_result:
                    collected_step_results.append(step_result)
            except Exception:
                pass
        yield event_str

    if user_id and collected_reply:
        try:
            await save_assistant_message(
                db,
                user_id=user_id,
                user_content=user_message.strip(),
                assistant_content=collected_reply,
                tools_used=collected_tools,
                conversation_id=conversation_id,
            )
        except Exception as e:
            logger.warning("[planning analysis·streaming] Failed to save session: %s", e)

        asyncio.create_task(
            _store_planned_analysis_memory(
                db,
                user_id,
                conversation_id or "",
                user_message.strip(),
                collected_reply,
                collected_tools,
                source,
            )
        )

    conv_id = conversation_id
    if user_id:
        thread = await get_or_create_assistant_thread(db, user_id, conversation_id)
        conv_id = thread["thread_id"]

    yield _sse(
        "done",
        {
            "reply": collected_reply,
            "tools_used": collected_tools,
            "conversation_id": conv_id,
            "plan": collected_plan,
            "step_results": collected_step_results,
            "source": source,
            "supplemented": supplemented,
        },
    )

