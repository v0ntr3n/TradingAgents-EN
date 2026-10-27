"""
Universal Agent (UniversalAgent)

A general-purpose agent driven entirely by database configuration that can replace 80-95% of specialized Agent classes.
All behaviors (tools, prompt words, output fields) are defined by the database configuration without any hard-coded business logic.

Design principles (refer to OpenClaw single responsibility):
- An Agent only does one thing: get the context → Get data with tools → write report
- Complexity is expressed through the workflow graph structure, not inside the Agent
- Three levels of priority: node exclusive > Workflow specific > Agent Default
"""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .base import BaseAgent
from .config import AgentConfig

logger = logging.getLogger(__name__)


class UniversalAgent(BaseAgent):
    """
    Universal Agent — Completely driven by database configuration

    Tool loading order (three levels of priority):
    1. Node specific:workflow_id + node_id + agent_id
    2. Workflow specific:workflow_id + agent_id
    3. Agent Default:agent_id only

    Prompt word loading order (implemented by the base class _get_prompt_from_template):
    1. Node-specific templates (workflow_id + node_id) 
    2. Workflow-specific template (workflow_id)
    3. Agent Default template
    4. Built-in default text
    """

    # Class-level metadata placeholder (dynamically set by the factory, here is None to satisfy the type annotation)
    metadata = None

    def __init__(
        self,
        config: Optional[AgentConfig] = None,
        llm: Optional[Any] = None,
        tool_ids: Optional[List[str]] = None,
        agent_id: str = "universal_agent",
        agent_name: str = "general agent",
        agent_description: str = "General-purpose agent driven by database configuration",
        output_field: str = "analysis_report",
        **kwargs,
    ):
        """
        Initialization general Agent

        Args:
            config: Agent Runtime configuration
            llm: LangChain LLM Example
            tool_ids: Tool ID list
            agent_id: Dynamic Agent ID (from agent_configs database)
            agent_name: Agent display name
            agent_description: Agent Description (used to build the default prompt word)
            output_field: Output field name (write the key of state)
        """
        # in super().__init__() Set dynamic properties before, because the parent class initialization will call self.agent_id
        self._dynamic_agent_id = agent_id
        self._agent_name = agent_name
        self._agent_description = agent_description
        self._output_field = output_field
        self._last_tool_debug = []
        self._last_llm_debug = {}
        # Agent Workshop Debug state: testing version + debug template
        self._version_status = kwargs.pop('version_status', None)
        self._prompt_template_id = kwargs.pop('prompt_template_id', None)

        super().__init__(config=config, llm=llm, tool_ids=tool_ids)

    @property
    def agent_id(self) -> str:
        """Returns dynamic Agent ID (from database configuration)"""
        return getattr(self, "_dynamic_agent_id", "universal_agent")

    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Common execution logic

        1. Loading system prompt words from the template system (supports workflow_id + node_id Three levels of priority)
        2. Load user prompts from the template system (or build generic user prompts)
        3. call LLM + Tools
        4. Output to state[output_field]
        """
        logger.info(f"[UniversalAgent:{self.agent_id}] 🚀 Start execution")

        # P1: Start execution trace collection
        from core.agents.execution_trace_recorder import (
            start_execution_trace, is_trace_enabled
        )
        recorder = None
        if is_trace_enabled():
            try:
                recorder = start_execution_trace(self, state)
                self._last_trace_id = recorder.trace_id
            except Exception as e:
                logger.warning(f"⚠️ [UniversalAgent:{self.agent_id}] Failed to start trajectory collection (does not affect agent): {e}")
                self._last_trace_id = None

        try:
            context = state.get("context")
            prompt_variables = self._build_prompt_variables(state)

            # 🔥 Agent Workshop Context injection:workflow_id + debug state flag
            if isinstance(context, dict):
                workflow_id = state.get("workflow_id")
                if workflow_id and "workflow_id" not in context:
                    context["workflow_id"] = workflow_id
                version_status = getattr(self, '_version_status', None)
                prompt_template_id = getattr(self, '_prompt_template_id', None)
                if version_status == "testing" and prompt_template_id:
                    context["is_debug_mode"] = True
                    context["debug_template_id"] = prompt_template_id
            elif context is not None:
                workflow_id = state.get("workflow_id")
                if workflow_id and not hasattr(context, 'workflow_id'):
                    context.workflow_id = workflow_id
                version_status = getattr(self, '_version_status', None)
                prompt_template_id = getattr(self, '_prompt_template_id', None)
                if version_status == "testing" and prompt_template_id:
                    context.is_debug_mode = True
                    context.debug_template_id = prompt_template_id

            # 1. System prompt words (from template system, three levels of priority)
            system_prompt = self._get_prompt_from_template(
                agent_type="universal",
                agent_name=self.agent_id,
                variables=prompt_variables,
                state=state,
                context=context,
                fallback_prompt=None,
                prompt_type="system",
            )

            if not system_prompt:
                system_prompt = self._build_default_system_prompt()

            # 2. User prompt words (from template system, three levels of priority)
            user_prompt = self._get_prompt_from_template(
                agent_type="universal",
                agent_name=self.agent_id,
                variables=prompt_variables,
                state=state,
                context=context,
                fallback_prompt=None,
                prompt_type="user",
            )

            if not user_prompt:
                user_prompt = self._build_default_user_prompt(state)
            else:
                user_prompt = self._ensure_runtime_context(user_prompt, state)

            # 🔥 Apply prompt_overrides (allows template content to be overridden when testing)
            overrides = state.get("prompt_overrides") or {}
            if isinstance(overrides, dict) and overrides:
                override_sys = overrides.get("system_prompt") or overrides.get("system")
                override_user = overrides.get("user_prompt") or overrides.get("user")
                if override_sys:
                    logger.info(f"[UniversalAgent:{self.agent_id}] prompt_overrides.system_prompt Applied "
                                f"(original length {len(system_prompt)} → new length {len(str(override_sys))})")
                    system_prompt = str(override_sys)
                if override_user:
                    logger.info(f"[UniversalAgent:{self.agent_id}] prompt_overrides.user_prompt Applied "
                                f"(original length {len(user_prompt)} → new length {len(str(override_user))})")
                    user_prompt = str(override_user)
                # Also supports formats nested in content
                content_overrides = overrides.get("content") or {}
                if isinstance(content_overrides, dict):
                    if content_overrides.get("system_prompt") or content_overrides.get("system"):
                        system_prompt = str(content_overrides.get("system_prompt") or content_overrides.get("system"))
                        logger.info(f"[UniversalAgent:{self.agent_id}] prompt_overrides.content.system_prompt Applied")
                    if content_overrides.get("user_prompt") or content_overrides.get("user"):
                        user_prompt = str(content_overrides.get("user_prompt") or content_overrides.get("user"))
                        logger.info(f"[UniversalAgent:{self.agent_id}] prompt_overrides.content.user_prompt Applied")

            execution_guidance = self._build_execution_plan_guidance(state)
            if execution_guidance:
                system_prompt = f"{system_prompt}\n\n{execution_guidance}"
                logger.info(
                    f"[UniversalAgent:{self.agent_id}] Agent Workshop execution_plan run constraints injected "
                    f"(length {len(execution_guidance)})"
                )

            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]

            logger.info(f"[UniversalAgent:{self.agent_id}] System prompt length: {len(system_prompt)}")
            logger.info(f"[UniversalAgent:{self.agent_id}] User prompt length: {len(user_prompt)}")

            # P1: record Prompt
            if recorder:
                try:
                    recorder.record_inputs({"ticker": state.get("ticker"), "workflow_id": state.get("workflow_id")})
                    recorder.record_prompts(system_prompt, user_prompt)
                except Exception as e:
                    logger.debug(f"[UniversalAgent:{self.agent_id}] Record Prompt failure (does not affect agent): {e}")

            if not self._llm:
                raise ValueError("LLM not initialized")

            if self._langchain_tools:
                logger.info(
                    f"[UniversalAgent:{self.agent_id}] Use tools to call patterns,"
                    f"Number of tools: {len(self._langchain_tools)}"
                )
                report = self.invoke_with_tools(messages)
                self._last_llm_debug = {
                    "response_type": "tool_invoke",
                    "final_response_content": report,
                    "tool_mode": True,
                    "tool_trace": list(getattr(self, '_tool_call_summaries_collected', [])),
                }
            else:
                logger.warning(f"[UniversalAgent:{self.agent_id}] No tools, call directly LLM")
                import time as _time_llm
                _llm_start = _time_llm.time()
                response = self._llm.invoke(messages)
                _llm_duration_ms = int((_time_llm.time() - _llm_start) * 1000)
                report = response.content if hasattr(response, "content") else str(response)
                self._last_llm_debug = {
                    "response_type": type(response).__name__,
                    "final_response_content": report,
                    "tool_mode": False,
                    "tool_trace": list(self._last_tool_debug),
                }
                # P1: Logging LLM response
                if recorder:
                    try:
                        recorder.record_llm_response(response, llm_duration_ms=_llm_duration_ms)
                    except Exception as e:
                        logger.debug(f"[UniversalAgent:{self.agent_id}] Log LLM response failure (does not affect agent): {e}")

            # P1: Record parsed output
            if recorder:
                try:
                    recorder.record_parsed_output({"report": report[:500] if isinstance(report, str) else str(report)[:500]})
                except Exception as e:
                    logger.debug(f"[UniversalAgent:{self.agent_id}] Record parsing output failure (does not affect agent): {e}")

            is_debug_mode = bool(getattr(context, 'is_debug_mode', False)) if context else False
            if is_debug_mode:
                logger.info(f"[UniversalAgent:{self.agent_id}] debug mode Prompt - system:\n{system_prompt}")
                logger.info(f"[UniversalAgent:{self.agent_id}] debug mode Prompt - user:\n{user_prompt}")
                logger.info(f"[UniversalAgent:{self.agent_id}] Debug mode LLM eventually returns:\n{self._last_llm_debug.get('final_response_content', report)}")

            logger.info(f"[UniversalAgent:{self.agent_id}] ✅ Execution is completed, output to '{self._output_field}'")
            result = {self._output_field: report}
            if is_debug_mode:
                result["__debug_prompt__"] = {
                    "system_prompt": system_prompt,
                    "user_prompt": user_prompt,
                    "llm_final_response": self._last_llm_debug.get("final_response_content", report),
                    "response_type": self._last_llm_debug.get("response_type"),
                    "tool_mode": self._last_llm_debug.get("tool_mode"),
                    "tool_trace": self._last_llm_debug.get("tool_trace", []),
                }
            return result

        except Exception as e:
            logger.error(f"[UniversalAgent:{self.agent_id}] ❌ Execution failed: {e}", exc_info=True)
            # P1: Log exception
            if recorder:
                try:
                    recorder.record_error(e)
                except Exception:
                    pass
            return {self._output_field: f"Execution failed: {str(e)}"}
        finally:
            # P1: Complete trajectory collection and write to MongoDB (non-blocking)
            if recorder:
                try:
                    recorder.finish()
                except Exception:
                    pass

    def _build_execution_plan_guidance(self, state: Dict[str, Any]) -> str:
        """Inject Agent Workshop execution_plan into runtime prompt words.

        build_version The generated execution_plan is a version execution contract and cannot just be left in the evaluation phase.
        Runtime These steps, tools, and acceptance items must be seen before the first tool call, otherwise the LLM may just
        Generate reports with broad role prompts, skipping version declarations for key tools.
        """
        plan = state.get("agent_workshop_execution_plan")
        if not isinstance(plan, dict) or not plan:
            return ""

        lines = [
            "## Agent Workshop Execution Plan (Strong constraints at runtime)",
            "The following is from the build_version execution plan for the current version. You have to follow it, not just follow the role description.",
        ]

        sample_input = plan.get("sample_input") if isinstance(plan.get("sample_input"), dict) else {}
        if sample_input:
            sample_parts = []
            for key in ("symbol", "market_type", "analysis_date", "task_description"):
                value = sample_input.get(key)
                if value:
                    sample_parts.append(f"{key}={value}")
            if sample_parts:
                lines.append(f"- Default sample/task context:{'; '.join(sample_parts)}")

        steps = plan.get("execution_steps") if isinstance(plan.get("execution_steps"), list) else []
        required_tools = []
        if steps:
            lines.append("- Execution steps:")
            for index, step in enumerate(steps[:6], 1):
                if not isinstance(step, dict):
                    continue
                title = str(step.get("title") or step.get("step_id") or f"step-{index}").strip()
                objective = str(step.get("objective") or "").strip()
                tools = [str(item).strip() for item in (step.get("suggested_tools") or []) if str(item).strip()]
                expected = [str(item).strip() for item in (step.get("expected_evidence") or []) if str(item).strip()]
                required_tools.extend(tools)
                line = f"  {index}. {title}"
                if objective:
                    line += f"：{objective}"
                lines.append(line)
                if tools:
                    lines.append(f"     - In this step, priority should be given to calling tools:{', '.join(tools)}")
                if expected:
                    lines.append(f"     - This step must form evidence:{'; '.join(expected[:4])}")

        required_tools = list(dict.fromkeys(required_tools))
        if required_tools:
            lines.append(f"- Requirements for calling key tools: If this task involves the core capabilities corresponding to these tools, the following must be called first:{', '.join(required_tools)}. ")
            lines.append("- If a key tool cannot be called or returns no data, the cause of the failure and the degradation boundary must be stated in the report, and other generalized reports cannot be used to pretend to be the results of the tool.")

        checks = [str(item).strip() for item in (plan.get("acceptance_checks") or []) if str(item).strip()]
        if checks:
            lines.append("- Self-inspection items before delivery:")
            for item in checks[:8]:
                lines.append(f"  - {item}")

        fallback_rules = [str(item).strip() for item in (plan.get("fallback_rules") or []) if str(item).strip()]
        if fallback_rules:
            lines.append("- Downgrade rules:")
            for item in fallback_rules[:6]:
                lines.append(f"  - {item}")

        lines.append("- It is strictly forbidden to write prompt presentation-style reports; the final conclusion must be able to correspond to tool calls, upstream structured input, or clear data gap descriptions.")
        return "\n".join(lines)

    def _build_prompt_variables(self, state: Dict[str, Any]) -> Dict[str, Any]:
        ticker = state.get("ticker") or state.get("stock_symbol") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date") or state.get("trade_date", "")
        return {
            "ticker": ticker,
            "stock_symbol": state.get("stock_symbol") or ticker,
            "company_of_interest": state.get("company_of_interest") or ticker,
            "analysis_date": analysis_date,
            "trade_date": state.get("trade_date") or analysis_date,
            "market_type": state.get("market_type", ""),
            "task_description": state.get("task_description", ""),
        }

    def _ensure_runtime_context(self, user_prompt: str, state: Dict[str, Any]) -> str:
        ticker = state.get("ticker") or state.get("stock_symbol") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date") or state.get("trade_date", "")
        market_type = state.get("market_type", "")
        task_description = state.get("task_description", "")

        context_lines = []
        if ticker:
            context_lines.append(f"- Stock code: {ticker}")
        if analysis_date:
            context_lines.append(f"- Analysis date: {analysis_date}")
        if market_type:
            context_lines.append(f"- market: {market_type}")
        if task_description:
            context_lines.append(f"- mission objectives: {task_description}")

        if not context_lines:
            return user_prompt

        context_block = "\n\n Input for this task:\n" + "\n".join(context_lines)
        if ticker and str(ticker) in user_prompt:
            return user_prompt
        return f"{user_prompt.rstrip()}{context_block}"

    def _build_default_system_prompt(self) -> str:
        """Build default system prompt words (used when the template system has no corresponding template)"""
        return f"""you are a professional{self._agent_name}. 

{self._agent_description}

Working principles:
1. Analyze based on real data obtained by tools, no fabrication or guessing
2. The conclusion is clear, well-founded and logically clear
3. Use Chinese output, clear format structure
4. If the data returned by the tool is missing a certain dimension, please explain"The data in this dimension is missing and will not be analyzed for the time being."

Please call the corresponding tool to obtain data according to the user s request, and then write a detailed analysis report."""

    def _build_default_user_prompt(self, state: Dict[str, Any]) -> str:
        """Build default user prompt words (used when the template system has no corresponding template)"""
        ticker = state.get("ticker") or state.get("company_of_interest", "")
        analysis_date = state.get("analysis_date") or state.get("trade_date", "")

        if ticker and analysis_date:
            return (
                f"Please analyze {ticker} ({analysis_date}) . "
                f"Please call the tool to obtain relevant data and then generate a detailed analysis report."
            )
        elif ticker:
            return f"please {ticker} Conduct a comprehensive analysis and use tools to obtain relevant data and generate detailed reports."
        else:
            return "Please call the required tools to obtain data and generate detailed analysis reports based on your role and responsibilities."

