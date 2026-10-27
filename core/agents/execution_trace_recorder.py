"""Agent Execution trajectory collector

Design principles:
1. Non-blocking: All exceptions are caught internally and do not affect agent execution
2. Progressive collection: record_prompts / record_llm_response / record_parsed_output step-by-step call
3. Subclass backfill: After the base is written, the subclass backfills the verification results through update_validation_sync
4. Configuration switch: settings.AGENT_EXECUTION_TRACE_ENABLED controls whether to enable
"""

# Annotation inertia: After the community version eliminates the execution_trace model, type annotations (such as trace -> AgentExecutionTrace) 
# Not evaluated when def is executed to avoid NameError; must be placed before other imports
from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from typing import Any, Dict, Optional

from app.core.config import settings
from app.utils.timezone import now_tz

# Optional import of backend dependencies: Community Edition (Apache 2.0 Open Source Edition) has added app/models/execution_trace with
# app/services/execution_trace_service Separate culling comes with Pro open source. When import fails, this module
# Downgrade to no-op (is_trace_enabled constant False → caller recorder constant None → All collection segments are skipped),
# 8 callers (analyst/researcher/manager/universal/base/trader_v2/fundamentals_analyst_v2/
# workflow builder) There are zero changes, and the main link of the community version analysis is not affected.
try:
    from app.pro.models.execution_trace import (
        AgentExecutionTrace,
        InputSnapshot,
        LLMConfigSnapshot,
        OutputSnapshot,
        PromptSnapshot,
        TokenUsage,
        ToolCallRecord,
        ValidationResult,
    )
    from app.pro.services.execution_trace_service import execution_trace_service
    _TRACE_BACKEND_AVAILABLE = True
except ImportError:  # Community Edition Path: Execution trace backend is not available
    _TRACE_BACKEND_AVAILABLE = False

logger = logging.getLogger(__name__)

# Thread local variables: supports temporarily opening trajectory collection for a single analysis task
# When the global switch is turned off, you can use enable_trace_for_current_thread() Temporarily open in the current thread
_trace_thread_local = threading.local()


def enable_trace_for_current_thread() -> None:
    """Temporarily enable trajectory collection for the current thread (single analysis task level)"""
    _trace_thread_local.enabled = True


def disable_trace_for_current_thread() -> None:
    """Close the temporary trajectory collection of the current thread"""
    _trace_thread_local.enabled = False


def is_trace_enabled() -> bool:
    """Check whether trajectory collection is enabled

    Priority: Backend availability > Thread local temporary mark > Global configuration
    - Backend is unavailable (community version) constant False
    - Global configuration AGENT_EXECUTION_TRACE_ENABLED is turned off by default
    - Analysis tasks can be done through enable_trace=true Parameters are temporarily enabled (only effective for this execution)
    """
    # The backend is not available (the execution_trace system has been removed from the community version)→ Always closed
    if not _TRACE_BACKEND_AVAILABLE:
        return False
    # Thread local tags take precedence
    if getattr(_trace_thread_local, "enabled", False):
        return True
    # Global configuration
    return getattr(settings, "AGENT_EXECUTION_TRACE_ENABLED", False)


class ExecutionTraceRecorder:
    """Execution trajectory collector

    Usage (in ManagerAgent.execute):
        recorder = start_execution_trace(self, state)
        try:
            recorder.record_inputs(inputs)
            recorder.record_prompts(system_prompt, user_prompt)
            response = self._llm.invoke(messages)
            recorder.record_llm_response(response, llm_duration_ms=500)
            decision = self._parse_response(response.content)
            recorder.record_parsed_output(decision)
            return result
        except Exception as e:
            recorder.record_error(e)
            raise
        finally:
            recorder.finish()  # Writing to MongoDB (non-blocking)

    Subclass backfill (in RiskManagerV2.execute):
        result = super().execute(state)
        # ... Verification ...
        self._record_trace_validation("passed"/"failed", error, details)
    """

    def __init__(
        self,
        agent_id: str,
        agent_version: str,
        agent_type: str,
        manager_type: Optional[str],
        state: Dict[str, Any],
    ):
        self._trace = AgentExecutionTrace(
            trace_id=str(uuid.uuid4()),
            agent_id=agent_id,
            agent_version=agent_version,
            agent_type=agent_type,
            manager_type=manager_type,
            started_at=now_tz(),
        )
        self._finished = False
        self._llm_duration_ms: Optional[int] = None

        # Extract workflow context from state
        self._extract_workflow_context(state)

        # Extract analysis targets
        self._trace.ticker = state.get("ticker") or state.get("company_of_interest")
        self._trace.analysis_date = state.get("analysis_date") or state.get("trade_date") or state.get("end_date")

    def _extract_workflow_context(self, state: Dict[str, Any]) -> None:
        """from state["_workflow_runtime"] Extract workflow context"""
        runtime = state.get("_workflow_runtime") or {}
        if isinstance(runtime, dict):
            self._trace.workflow_id = runtime.get("workflow_id")
            self._trace.execution_id = runtime.get("execution_id")
            self._trace.task_id = runtime.get("task_id") or runtime.get("execution_id")
            self._trace.user_id = runtime.get("user_id")
            self._trace.thread_id = runtime.get("thread_id")

    def record_llm_config(self, llm: Any) -> None:
        """Document LLM configuration"""
        try:
            self._trace.llm_config = LLMConfigSnapshot(
                model_name=getattr(llm, "model_name", None) or getattr(llm, "model", None),
                temperature=getattr(llm, "temperature", None),
                max_tokens=getattr(llm, "max_tokens", None),
            )
        except Exception as e:
            logger.debug(f"Logging LLM configuration failure: {e}")

    def record_inputs(self, inputs: Dict[str, Any]) -> None:
        """Record input snapshot"""
        try:
            input_lengths = {}
            for k, v in inputs.items():
                try:
                    input_lengths[k] = len(str(v)) if v else 0
                except Exception:
                    input_lengths[k] = 0
            self._trace.inputs = InputSnapshot(
                input_keys=list(inputs.keys()),
                input_lengths=input_lengths,
            )
        except Exception as e:
            logger.debug(f"Logging input snapshot failed: {e}")

    def record_prompts(self, system_prompt: str, user_prompt: str) -> None:
        """Record prompt word snapshot (hash + length + Full text)

        Full-text storage is used for: front-end viewing, prompt optimization comparison, and regression test replay.
        Hash/length preserving hash clustering for P2 reflective scans (small size, fast scans).
        """
        try:
            self._trace.prompts = PromptSnapshot(
                system_prompt_hash=hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:16] if system_prompt else None,
                system_prompt_length=len(system_prompt) if system_prompt else 0,
                user_prompt_hash=hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()[:16] if user_prompt else None,
                user_prompt_length=len(user_prompt) if user_prompt else 0,
                system_prompt_full=system_prompt if system_prompt else None,
                user_prompt_full=user_prompt if user_prompt else None,
            )
        except Exception as e:
            logger.debug(f"Failed to record prompt word snapshot: {e}")

    def record_llm_response(self, response: Any, llm_duration_ms: Optional[int] = None) -> None:
        """Logging LLM response

        Supports accumulation of multiple calls:
        - In tool call mode, LLM will be called multiple times (each cycle + final report)
        - The Token usage for each call is accumulated to the total usage.
        - The output snapshot only retains the last (final report) but the number of LLM calls +1
        """
        try:
            # 🔑 Cumulative number of LLM calls
            self._trace.llm_call_count += 1

            # Cumulative LLM time consumption
            if llm_duration_ms is not None:
                prev = self._llm_duration_ms or 0
                self._llm_duration_ms = prev + llm_duration_ms

            # Output snapshot (overlay, retain final report)
            content = getattr(response, "content", "") or ""
            if content:
                self._trace.output = OutputSnapshot(
                    output_raw_length=len(content),
                    output_raw_preview=content[:500] if content else None,
                    output_raw_full=content if content else None,
                )

            # Token Usage accumulation (compatible with LangChain AIMessage)
            usage_meta = getattr(response, "usage_metadata", None)
            if isinstance(usage_meta, dict):
                prev_input = self._trace.token_usage.input_tokens or 0
                prev_output = self._trace.token_usage.output_tokens or 0
                prev_total = self._trace.token_usage.total_tokens or 0
                self._trace.token_usage = TokenUsage(
                    input_tokens=prev_input + (usage_meta.get("input_tokens") or 0),
                    output_tokens=prev_output + (usage_meta.get("output_tokens") or 0),
                    total_tokens=prev_total + (usage_meta.get("total_tokens") or 0),
                )

            # Completion from response_metadata model_name
            resp_meta = getattr(response, "response_metadata", None)
            if isinstance(resp_meta, dict):
                model_from_resp = resp_meta.get("model_name") or resp_meta.get("model")
                if model_from_resp and not self._trace.llm_config.model_name:
                    self._trace.llm_config.model_name = model_from_resp
        except Exception as e:
            logger.debug(f"Logging LLM response failure: {e}")

    def record_tool_call(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool = True,
        error: Optional[str] = None,
        result_length: int = 0,
        result_preview: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> None:
        """Record a tool call"""
        try:
            self._trace.tool_calls.append(ToolCallRecord(
                tool_name=tool_name,
                tool_args=tool_args,
                success=success,
                error=error[:500] if error else None,
                result_length=result_length,
                result_preview=result_preview[:200] if result_preview else None,
                duration_ms=duration_ms,
            ))
        except Exception as e:
            logger.debug(f"Recording tool call failed: {e}")

    def record_parsed_output(self, parsed: Any) -> None:
        """Record parsed output"""
        try:
            if isinstance(parsed, dict):
                self._trace.output.output_parsed_keys = list(parsed.keys())
                self._trace.output.output_parsed_success = parsed.get("success", True)
                self._trace.output.output_parsed_type = "dict"
            else:
                self._trace.output.output_parsed_type = type(parsed).__name__
                self._trace.output.output_parsed_success = True
        except Exception as e:
            logger.debug(f"Log parsing output failed: {e}")

    def record_error(self, exc: Exception) -> None:
        """Log exception"""
        self._trace.success = False
        self._trace.error_message = str(exc)
        self._trace.error_type = type(exc).__name__

    @property
    def trace_id(self) -> str:
        return self._trace.trace_id

    @property
    def trace(self) -> AgentExecutionTrace:
        """Expose trace objects (for scenarios such as TraderV2 that require direct operation)"""
        return self._trace

    def finish(self) -> None:
        """Complete collection and write to MongoDB (non-blocking)"""
        if self._finished:
            return
        self._finished = True
        try:
            self._trace.finished_at = now_tz()
            duration_ms = int(
                (self._trace.finished_at - self._trace.started_at).total_seconds() * 1000
            )
            self._trace.execution_duration_ms = duration_ms
            self._trace.llm_duration_ms = self._llm_duration_ms
            execution_trace_service.save_trace_sync(self._trace)
        except Exception as e:
            logger.warning(f"⚠️ Execution trace finish failed (does not affect agent): {e}")

    def set_validation(
        self,
        validation_status: str,
        validation_error: Optional[str] = None,
        validation_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Backfill the verification results into the memory trace object (to be written together when finish).

        Solve the trader_v2 timing problem: record_trace_validation (DB update) of trader_v2
        Executed before finish (insert), the document does not exist at this time, causing update no-op.
        Then the insert of finish uses the memory validation=None cover.

        This method updates the validation field of the memory object so that the insert of finish carries the correct value.
        If it has been finished (the document has been inserted), it will be downgraded to DB update (compatible with ManagerAgent
        in super().execute finally Scenarios where finish first and backfill after subclassing).
        """
        try:
            if self._trace.validation is None:
                self._trace.validation = ValidationResult()
            self._trace.validation.validation_status = validation_status
            if validation_error is not None:
                self._trace.validation.validation_error = validation_error
            if validation_details is not None:
                self._trace.validation.validation_details = validation_details
        except Exception as e:
            logger.debug(f"Failed to record verification results into memory: {e}")
        # If the document has been inserted (finish has been executed), it will be updated synchronously. DB
        if self._finished:
            record_trace_validation(
                trace_id=self._trace.trace_id,
                validation_status=validation_status,
                validation_error=validation_error,
                validation_details=validation_details,
            )


def start_execution_trace(
    agent: Any,
    state: Dict[str, Any],
) -> ExecutionTraceRecorder:
    """Start execution trace collection

    Args:
        agent: Agent Instance (requires agent_id, get_metadata attributes)
        state: Workflow status

    Returns:
        ExecutionTraceRecorder Example
    """
    # 🔑 Anti-duplication: If the agent already has an active recorder, return directly (to avoid repeated creation of the builder layer and adapter layer)
    existing = getattr(agent, "_execution_recorder", None)
    if existing is not None and not existing._finished:
        return existing

    metadata = agent.get_metadata() if hasattr(agent, "get_metadata") else None
    agent_version = getattr(metadata, "version", "unknown") if metadata else "unknown"
    manager_type = getattr(agent, "manager_type", None)

    # Determine agent_type (distinguished by base class type identification attribute)
    if manager_type is not None:
        agent_type = "manager"
    elif getattr(agent, "analyst_type", None) is not None:
        agent_type = "analyst"
    elif getattr(agent, "researcher_type", None) is not None:
        agent_type = "researcher"
    elif hasattr(agent, "output_field"):
        agent_type = "trader"
    else:
        agent_type = "manager"  # Default to cover up

    recorder = ExecutionTraceRecorder(
        agent_id=agent.agent_id,
        agent_version=agent_version,
        agent_type=agent_type,
        manager_type=manager_type,
        state=state,
    )

    # Document LLM configuration
    if hasattr(agent, "_llm") and agent._llm is not None:
        recorder.record_llm_config(agent._llm)

    # 🔑 Automatically bind the recorder to the agent so that invoke_with_tools can automatically record the LLM response
    # In this way, all adapters that inherit BaseAgent (such as fundamentals_analyst_v2, etc.) will automatically record Token usage
    try:
        agent._execution_recorder = recorder
    except Exception:
        pass

    return recorder


def record_trace_validation(
    trace_id: Optional[str],
    validation_status: str,
    validation_error: Optional[str] = None,
    validation_details: Optional[Dict[str, Any]] = None,
) -> None:
    """Backfill verification results (for subclass calls, non-blocking)"""
    if not trace_id or not is_trace_enabled():
        return
    try:
        execution_trace_service.update_validation_sync(
            trace_id=trace_id,
            validation_status=validation_status,
            validation_error=validation_error,
            validation_details=validation_details,
        )
    except Exception as e:
        logger.warning(f"⚠️ Backfill verification result fails (does not affect agent): {e}")
