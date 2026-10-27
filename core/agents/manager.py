"""
ManagerAgent base class

Used to implement manager agents (research integrators, risk assessors, etc.)
v2.0 New: configuration-based manager Agent architecture
"""

import logging
import json
from abc import abstractmethod
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from .base import BaseAgent
from .config import AgentMetadata, AgentCategory

logger = logging.getLogger(__name__)


def _stringify_manager_decision(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True)
        except TypeError:
            return str(value)
    return str(value)


class ManagerAgent(BaseAgent):
    """
    ManagerAgent base class
    
    Work mode: Host debate/review → Comprehensive opinions from various parties → form final research conclusions
    
    Features:
    - Do not call tools
    - Rely on the output of multiple agents
    - Need debate status management
    - Output format: Decision/Plan
    
    Workflow:
    1. Read multiple view reports from state
    2. Moderate debate (optional)
    3. Comprehensive research and judgment using LLM
    4. Generate final research conclusions
    5. Output to state["investment_plan"/"risk_assessment"]
    
    Subclasses need to implement:
    - _build_system_prompt(): Build system prompt words
    - _build_user_prompt(): Build user prompt words
    - _get_required_inputs(): Get the required input list
    """
    
    # Manager type (subclass definition)
    manager_type: str = None
    
    # Output field name (subclass definition)
    output_field: str = None
    
    # Is it necessary to debate
    enable_debate: bool = False
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        memory: Optional[Any] = None,
        debate_rounds: int = 1,
        **kwargs
    ):
        """
        initialization manager Agent
        
        Args:
            config: Agent Configuration
            llm: LLM Example
            debate_rounds: Debate rounds
            **kwargs: Other parameters
        """
        super().__init__(config=config, llm=llm, **kwargs)
        
        self.memory = memory
        self.debate_rounds = debate_rounds
        self.debate_history = []
        self._last_trace_id = None  # P1: Execution track ID (for subclasses to backfill verification results)
        self._last_assertion_result = None  # P2: The latest assertion execution result (for reference by subclasses)

        logger.debug(f"ManagerAgent '{self.agent_id}' Initialization completed")

    def delegate_to_agent(
        self,
        target_agent_id: str,
        state: Dict[str, Any],
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Manager s semantic packaging: delegate special tasks to sub-Agents for execution."""
        logger.info(f"[ManagerAgent] {self.agent_id} Start delegation Agent: {target_agent_id}")
        result = self.invoke_agent(
            target_agent_id=target_agent_id,
            state=state,
            payload=payload,
            metadata={
                "manager_type": self.manager_type,
                **(metadata or {}),
            },
        )
        logger.info(f"[ManagerAgent] {self.agent_id} Delegate sub-Agent to complete: {target_agent_id}")
        return result
    
    def execute(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        implement management decisions

        Args:
            state: Workflow status dictionary, including:
                - ticker: Stock code
                - analysis_date: Analysis date
                - bull_report: Positive Evidence Research Observation (optional)
                - bear_report: Careful Evidence Research Observation (optional)
                - trade_info: Transaction information (transaction review scenario)
                - Other inputs...

        Returns:
            Updated status dictionary containing decision results
        """
        logger.info(f"Start execution manager Agent: {self.agent_id}")

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
                logger.warning(f"⚠️ Failed to start trajectory collection (does not affect agent): {e}")
                self._last_trace_id = None

        try:
            # 🔍 Debug log: troubleshooting ticker loss problem
            logger.error(
                f"🔍 [{self.agent_id}] state keys: {list(state.keys())[:20]}, "
                f"ticker={state.get('ticker')}, company_of_interest={state.get('company_of_interest')}, "
                f"trade_info exist={('trade_info' in state)}, code={state.get('trade_info', {}).get('code') if isinstance(state.get('trade_info'), dict) else 'N/A'}"
            )

            # 1. Extract input parameters (unified use of base class methods, compatible with various field names and scenarios)
            ticker, analysis_date = self._extract_common_params(state)

            if not ticker:
                raise ValueError("Missing required parameters: ticker")
            
            # 2. Gather the required input
            inputs = self._collect_inputs(state)
            if recorder:
                recorder.record_inputs(inputs)

            if not inputs:
                raise ValueError("No inputs available for decision making")
            
            # 3. If debate is enabled, debate
            if self.enable_debate:
                debate_summary = self._conduct_debate(inputs, state)
            else:
                debate_summary = None

            memory_context = self._get_memory_context(ticker, inputs)
            if memory_context:
                debate_summary = self._merge_memory_context(debate_summary, memory_context)
            
            # 4. Build prompt words
            logger.info(f"🔍 [{self.agent_id}] Start building prompt words...")
            # 🔑 Pass the state parameter (subclasses can extract variables from state such as company_name, ticker etc.)
            system_prompt = self._build_system_prompt(state=state)
            logger.info(f"📝 [{self.agent_id}] System prompt word length: {len(system_prompt)} character")
            logger.info(f"📝 [{self.agent_id}] Complete system prompt word:\n{'='*80}\n{system_prompt}\n{'='*80}")

            user_prompt = self._build_user_prompt(ticker, analysis_date, inputs, debate_summary, state)
            logger.info(f"📝 [{self.agent_id}] User prompt word length: {len(user_prompt)} character")
            logger.info(f"📝 [{self.agent_id}] Complete user prompt word:\n{'='*80}\n{user_prompt}\n{'='*80}")

            # 5. Call LLM to make decisions
            system_prompt = self._apply_global_trading_advice_guard(system_prompt)
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            if recorder:
                recorder.record_prompts(system_prompt, user_prompt)

            logger.info(f"System prompt word: {system_prompt}")
            logger.info(f"User prompt words: {user_prompt}")

            # Print the complete content finally sent to LLM (including all fields:system_prompt, tool_guidance, analysis_requirements, output_format, constraints, user_prompt) 
            final_system_content = system_prompt  # system_prompt All system-related parts have been included (combined through get_agent_prompt)
            final_user_content = user_prompt
            final_messages_text = f""" [SystemMessage - System prompt words (including system_prompt + tool_guidance + analysis_requirements + output_format + constraints) ] 
{final_system_content}

 [HumanMessage - User prompt words]
{final_user_content}"""
            
            total_length = len(final_system_content) + len(final_user_content)
            logger.info(f"📝 [{self.agent_id}] The full content length finally sent to LLM: {total_length} character")
            logger.info(f"📝 [{self.agent_id}] SystemMessage length: {len(final_system_content)} character")
            logger.info(f"📝 [{self.agent_id}] HumanMessage length: {len(final_user_content)} character")
            logger.info(f"📝 [{self.agent_id}] The complete content finally sent to LLM:\n{'='*80}\n{final_messages_text}\n{'='*80}")

            logger.info(f"🤖 [{self.agent_id}] Start calling LLM...")
            logger.info(f"🤖 [{self.agent_id}] LLM Type: {type(self._llm).__name__}")

            if self._llm:
                import time as _time
                _t0 = _time.time()
                response = self._llm.invoke(messages)
                _llm_duration_ms = int((_time.time() - _t0) * 1000)

                # 🛡️ Q1: Empty response line of defense——Inference model contingency"Transient exception"Returns empty content (HTTP successful but visible content is 0)
                # After recording finish_reason/thinking token, retreat and try again once; if it is still empty, take the failure path, and it is forbidden to package empty content as success.
                if not (getattr(response, "content", "") or "").strip():
                    _meta = getattr(response, "response_metadata", None) or {}
                    _usage = getattr(response, "usage_metadata", None) or {}
                    _reasoning = ((_usage.get("output_token_details") or {}).get("reasoning"))
                    logger.warning(
                        f"⚠️ [{self.agent_id}] LLM Return empty content(finish_reason={_meta.get('finish_reason')}, "
                        f"reasoning_tokens={_reasoning}, Time consuming={_llm_duration_ms}ms) , 5s Automatically retry 1 time after"
                    )
                    _time.sleep(5)
                    _t0 = _time.time()
                    response = self._llm.invoke(messages)
                    _llm_duration_ms = int((_time.time() - _t0) * 1000)
                    if not (getattr(response, "content", "") or "").strip():
                        _meta = getattr(response, "response_metadata", None) or {}
                        raise ValueError(
                            f"LLM Returns empty content (still empty after 1 retry,finish_reason={_meta.get('finish_reason')}) "
                        )

                if recorder:
                    recorder.record_llm_response(response, llm_duration_ms=_llm_duration_ms)
                logger.info(f"✅ [{self.agent_id}] LLM Call successful")
                logger.info(f"📝 [{self.agent_id}] LLM response length: {len(response.content)} character")
                logger.info(f"📝 [{self.agent_id}] Full LLM response:\n{'='*80}\n{response.content}\n{'='*80}")

                decision = self._parse_response(response.content)
                if recorder:
                    recorder.record_parsed_output(decision)
                logger.info(f"✅ [{self.agent_id}] Response parsed successfully")
                logger.info(f"📝 [{self.agent_id}] Parse result type: {type(decision)}")
                logger.info(f"📝 [{self.agent_id}] llm Returned parsing results: {decision}")

                # If it is a dictionary, record the key fields
                if isinstance(decision, dict):
                    logger.info(f"📝 [{self.agent_id}] Parse result fields: {list(decision.keys())}")
                    if "target_price" in decision or "price_analysis_range" in decision:
                        price_info = decision.get("target_price") or decision.get("price_analysis_range")
                        logger.info(f"💰 [{self.agent_id}] price analysis range: {price_info}")
                    if "action" in decision or "analysis_view" in decision or "market_view" in decision:
                        view = decision.get("action") or decision.get("analysis_view") or decision.get("market_view")
                        logger.info(f"🎯 [{self.agent_id}] market view: {view}")
                    if "confidence" in decision:
                        logger.info(f"📊 [{self.agent_id}] Confidence: {decision.get('confidence')}")

                self._save_to_memory(ticker, decision)
            else:
                raise ValueError("LLM not initialized")
            
            # 6. Output to state (only newly added fields are returned to avoid concurrency conflicts)
            output_key = self.output_field or f"{self.manager_type}_decision"
            result = {
                output_key: decision
            }

            # 7. Save debate history (if available)
            if self.enable_debate and self.debate_history:
                result[f"{self.agent_id}_debate_history"] = self.debate_history

            logger.info(f"manager Agent {self.agent_id} Executed successfully")
            return result

        except Exception as e:
            if recorder:
                recorder.record_error(e)
            logger.error(f"manager Agent {self.agent_id} Execution failed: {e}", exc_info=True)
            # Return error status (only newly added fields are returned)
            output_key = self.output_field or f"{self.manager_type}_decision"
            return {
                output_key: {
                    "error": str(e),
                    "success": False
                }
            }
        finally:
            if recorder:
                recorder.finish()

    def _record_trace_validation(
        self,
        validation_status: str,
        validation_error: Optional[str] = None,
        validation_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """P1: Backfill the verification results into the execution trace (for calls by subclasses, non-blocking)"""
        from core.agents.execution_trace_recorder import record_trace_validation
        record_trace_validation(
            trace_id=self._last_trace_id,
            validation_status=validation_status,
            validation_error=validation_error,
            validation_details=validation_details,
        )

    def _run_assertions(
        self,
        raw_text: str,
        parsed: Optional[Dict[str, Any]] = None,
    ):
        """P2: Assertion to perform recall (non-blocking).

        Provide subclasses in _validate_* Called after completion. Return AssertionRunResult,
        It s up to subclasses to decide how to merge into validation_status.

        Try/except throughout, return on failure AssertionRunResult(ran=False), 
        Does not affect the agent main process.
        """
        from app.core.config import settings
        try:
            from app.pro.models.agent_assertion import AssertionRunResult
        except ImportError:
            # The community version has no assertion system (app/models/agent_assertion, etc. have been removed with the Pro open source separation):
            # Return"Not running"placeholder result, the caller violations/has_error_violation/error_count
            # The properties of are all safe to access (empty list + False) , Assert function is silently skipped overall
            from types import SimpleNamespace
            return SimpleNamespace(
                ran=False, violations=[], has_error_violation=False, error_count=0
            )
        if not getattr(settings, "AGENT_ASSERTION_ENABLED", True):
            return AssertionRunResult(ran=False)
        try:
            from core.agents.assertion_executor import assertion_executor
            result = assertion_executor.run_assertions_sync(
                agent_id=self.agent_id,
                raw_text=raw_text,
                parsed=parsed,
            )
            self._last_assertion_result = result
            return result
        except Exception as e:
            logger.warning(f"⚠️ [{self.agent_id}] Assertion execution failed (does not affect agent): {e}")
            return AssertionRunResult(ran=False)
    
    def _collect_inputs(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Gather the required input

        Args:
            state: Workflow status

        Returns:
            input dictionary
        """
        required_inputs = self._get_required_inputs()
        logger.info(f"🔍 [{self.agent_id}] required input fields: {required_inputs}")
        logger.info(f"🔍 [{self.agent_id}] State all fields in: {list(state.keys())}")

        inputs = {}

        for input_key in required_inputs:
            if input_key in state:
                value = state[input_key]
                inputs[input_key] = value
                logger.info(f"✅ [{self.agent_id}] find input: {input_key}, Type: {type(value)}, length: {len(str(value))} character")
            else:
                logger.warning(f"⚠️ [{self.agent_id}] missing input: {input_key}")

        logger.info(f"📝 [{self.agent_id}] collected {len(inputs)} input")

        return inputs
    
    def _conduct_debate(self, inputs: Dict[str, Any], state: Dict[str, Any]) -> str:
        """
        host debate
        
        Args:
            inputs: input dictionary
            state: Workflow status
            
        Returns:
            Debate summary
        """
        self.debate_history = []
        
        # Simplify implementation: directly summarize the views of all parties
        # The actual implementation can be debated in many rounds
        debate_summary = "Debate summary:\n"
        
        for key, value in inputs.items():
            if isinstance(value, dict) and "content" in value:
                debate_summary += f"\n{key}: {value['content'][:200]}...\n"
        
        self.debate_history.append({
            "round": 1,
            "summary": debate_summary
        })

        return debate_summary

    def _build_memory_query(self, ticker: str, inputs: Dict[str, Any]) -> str:
        query_parts = [f"Stock code: {ticker}", f"manager type: {self.manager_type or self.agent_id}", "historical management decisions"]
        for key, value in list(inputs.items())[:4]:
            if not value:
                continue
            content = value.get("content") if isinstance(value, dict) else str(value)
            query_parts.append(f"{key}: {str(content)[:200]}")
        return "\n".join(query_parts)

    def _get_memory_context(self, ticker: str, inputs: Dict[str, Any]) -> str:
        if not self.memory:
            return ""

        try:
            query = self._build_memory_query(ticker, inputs)

            if not hasattr(self.memory, "search_memories"):
                logger.warning("Memory instances do not support search_memories, manager history recall has been skipped: %s", type(self.memory).__name__)
                return ""

            memories = self.memory.search_memories(
                query=query,
                n_results=3,
                filter_metadata={"ticker": ticker} if ticker else None,
            )
            formatted = []
            for item in memories or []:
                content = item.get("content", "")
                similarity = item.get("similarity", 0.0)
                if content:
                    formatted.append(f"[Similarity: {similarity:.2f}] {content}")
            if formatted:
                return " [Historical management experience]\n" + "\n\n".join(formatted)
        except Exception as exc:
            logger.warning(f"Failed to obtain manager history memory: {exc}")

        return ""

    def _merge_memory_context(self, debate_summary: Optional[str], memory_context: str) -> str:
        if debate_summary:
            return f"{debate_summary}\n\n{memory_context}"
        return memory_context

    def _save_to_memory(self, ticker: str, decision: Any) -> None:
        if not self.memory:
            return

        try:
            content = _stringify_manager_decision(decision)

            if not hasattr(self.memory, "add_memory"):
                logger.warning("Memory instances do not support add_memory and manager memory saving has been skipped: %s", type(self.memory).__name__)
                return

            metadata = {
                "ticker": ticker,
                "agent_id": self.agent_id,
                "manager_type": self.manager_type,
                "output_field": self.output_field,
                "memory_kind": "manager_decision",
                "source": "manager_agent_runtime",
            }
            self.memory.add_memory(content=content, metadata=metadata)
        except Exception as exc:
            logger.warning(f"Failed to save manager memory: {exc}")

    @abstractmethod
    def _build_system_prompt(self, state: Dict[str, Any] = None) -> str:
        """
        Build system prompt words (subclass implementation)

        Args:
            state: Workflow status (optional, used to extract variables such as company_name, ticker etc.)

        Returns:
            System prompt word
        """
        pass

    @abstractmethod
    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        inputs: Dict[str, Any],
        debate_summary: Optional[str],
        state: Dict[str, Any]
    ) -> str:
        """
        Construct user prompt words (subclass implementation)

        Args:
            ticker: Stock code
            analysis_date: Analysis date
            inputs: Collection of input dictionaries
            debate_summary: Debate summary
            state: Workflow status

        Returns:
            User prompt words
        """
        pass

    @abstractmethod
    def _get_required_inputs(self) -> List[str]:
        """
        Get the required input list (subclass implementation)

        Returns:
            Enter a list of field names
        """
        pass

    # Note:_get_prompt_from_template() Method has been moved to BaseAgent base class, shared by all Agents

    def _parse_response(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM response (can be overridden by subclasses)

        Args:
            response: LLM response text

        Returns:
            Parsed decision dictionary
        """
        # Default implementation: return text directly
        return {
            "content": response,
            "success": True
        }

    @property
    def agent_id(self) -> str:
        """get Agent ID"""
        if self.metadata:
            return self.metadata.id
        return self.__class__.__name__.lower()

