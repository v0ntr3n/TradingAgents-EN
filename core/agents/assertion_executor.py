"""Agent assertexecutor(P2: Reflection lesson upgraded to executable assertion)

The recalled assertions are executed synchronously when the manager agent verifies, and the violation results are merged into validation_status.

Design principles:
1. Non-blocking: All exceptions are caught internally and do not affect agent execution
2. In-process cache: enabled assertions are cached by agent_id for 60s (managed by the service layer)
3. Result merging: Returns AssertionRunResult, merged from the base class into validation_status
4. Single isolation: Failure to execute a single assertion does not affect other assertions

Usage (in ManagerAgent._run_assertions):
    from core.agents.assertion_executor import assertion_executor
    result = assertion_executor.run_assertions_sync(
        agent_id=self.agent_id,
        raw_text=raw_text,
        parsed=parsed_dict,
    )
    if result.has_error_violation:
        # Downgrade validation_status
"""

# Annotation inertization: After the community version eliminates the agent_assertion model, type annotations (such as -> AssertionRunResult) 
# Not evaluated when def is executed to avoid NameError; must be placed before other imports
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, List, Optional

# Optional import of backend dependencies: Community Edition (Apache 2.0 Open Source Edition) has added app/models/agent_assertion with
# app/services/agent_assertion_service Separate culling comes with Pro open source. This module is downgraded when import fails:
# run_assertions_sync Directly raise, the caller (trader_v2/manager, both within try) catches the downgrade
try:
    from app.pro.models.agent_assertion import (
        AgentAssertion,
        AssertionRunResult,
        AssertionSeverity,
        AssertionType,
        AssertionViolation,
    )
    from app.pro.services.agent_assertion_service import agent_assertion_service
    _ASSERTION_BACKEND_AVAILABLE = True
except ImportError:  # Community Edition Path: Assert backend is unavailable
    _ASSERTION_BACKEND_AVAILABLE = False

logger = logging.getLogger(__name__)


def _get_field_by_path(parsed: Dict[str, Any], field_path: str) -> Any:
    """Get values from parsed dict by dotted path.

    For example field_path="final_trade_decision.action" from {"final_trade_decision": {"action": "optimistic"}} take out "optimistic". 
    Returns None if the path does not exist or has a value of None.
    """
    if not parsed or not field_path or field_path == "*":
        return None
    current: Any = parsed
    for part in field_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class AssertionExecutor:
    """assertion executor"""

    def __init__(self):
        # Thread lock for asynchronous triggering of hit count (to avoid concurrent log writing)
        self._hit_lock = threading.Lock()

    def run_assertions_sync(
        self,
        agent_id: str,
        raw_text: str,
        parsed: Optional[Dict[str, Any]] = None,
    ) -> AssertionRunResult:
        """Synchronous execution of assertions (called in the context of manager agent execute).

        Try/except throughout, return on failure AssertionRunResult(ran=False). 
        """
        # The backend is unavailable (the community version has eliminated the assertion system)→ Throws, caller try/except downgrade
        if not _ASSERTION_BACKEND_AVAILABLE:
            raise ImportError("Assert that the backend is unavailable (the community version does not have the agent_assertion system)")
        try:
            # 1. Load enabled assertions (with cache, managed by service layer)
            assertions = agent_assertion_service.load_enabled_assertions_sync(agent_id)
            if not assertions:
                return AssertionRunResult(ran=False)

            # 2. Distribute execution by assertion_type
            violations: List[AssertionViolation] = []
            hit_assertion_ids: List[str] = []

            for assertion in assertions:
                violation = self._run_single_assertion(assertion, raw_text, parsed)
                if violation is not None:
                    violations.append(violation)
                    hit_assertion_ids.append(assertion.assertion_id)

            # 3. Asynchronous trigger hit_count auto-increment (fire-and-forget, non-blocking)
            if hit_assertion_ids:
                self._fire_and_forget_hit_count(hit_assertion_ids)

            # 4. statistics
            error_count = sum(1 for v in violations if v.severity == AssertionSeverity.ERROR)
            warning_count = sum(1 for v in violations if v.severity == AssertionSeverity.WARNING)

            return AssertionRunResult(
                ran=True,
                violations=violations,
                has_error_violation=error_count > 0,
                error_count=error_count,
                warning_count=warning_count,
            )
        except Exception as e:
            logger.warning(f"⚠️ [AssertionExecutor] Assertion execution failed (does not affect agent): {e}")
            return AssertionRunResult(ran=False)

    def _run_single_assertion(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Execute a single assertion and return violation or None (no violation).

        Failure to execute a single assertion does not affect other assertions.
        """
        try:
            handler = self._HANDLERS.get(assertion.assertion_type)
            if handler is None:
                logger.warning(
                    f"⚠️ [AssertionExecutor] Unknown assertion type: {assertion.assertion_type} (skip)"
                )
                return None
            return handler(self, assertion, raw_text, parsed)
        except Exception as e:
            logger.warning(
                f"⚠️ [AssertionExecutor] Single assertion execution failed (skipped): assertion_id={assertion.assertion_id}, error={e}"
            )
            return None

    @staticmethod
    def _constraint_get(assertion: AgentAssertion, key: str, default: Any = None) -> Any:
        """Get value from constraint (compatible with pydantic extra fields).

        AssertionConstraint use extra="allow", extra Fields exist in __pydantic_extra__,
        __dict__ Can t get it, must use it model_dump(). 
        """
        try:
            return assertion.constraint.model_dump().get(key, default)
        except Exception:
            return default

    # ==================== 7 assertion type implementation ====================

    def _check_term_forbidden(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Disable term scanning (acts on raw text)"""
        terms = self._constraint_get(assertion, "terms") or []
        if not terms or not raw_text:
            return None

        hit_terms = [t for t in terms if t and t in raw_text]
        if hit_terms:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Disable term scanning",
                violation_detail=f"hit disabled term: {hit_terms}",
            )
        return None

    def _check_field_required(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Required field check (applies to parsed dict)"""
        field = self._constraint_get(assertion, "field") or assertion.target_field
        if not field or field == "*":
            return None
        if parsed is None:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Required field check",
                violation_detail=f"parsed is empty, field cannot be checked {field}",
            )
        value = _get_field_by_path(parsed, field)
        if value is None:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Required field check",
                violation_detail=f"Field missing: {field}",
            )
        return None

    def _check_field_enum(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Field enumeration constraints"""
        field = self._constraint_get(assertion, "field") or assertion.target_field
        allowed = self._constraint_get(assertion, "allowed") or []
        if not field or field == "*" or not allowed:
            return None
        if parsed is None:
            return None  # parsed No enumeration violation is reported when it is empty (reported by field_required)

        value = _get_field_by_path(parsed, field)
        if value is None:
            return None  # Missing fields are handled by field_required

        if value not in allowed:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Field enumeration constraints",
                violation_detail=f"Field {field}={value!r} Not in allowed value {allowed} within",
            )
        return None

    def _check_field_range(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Numeric field range constraints"""
        field = self._constraint_get(assertion, "field") or assertion.target_field
        min_val = self._constraint_get(assertion, "min")
        max_val = self._constraint_get(assertion, "max")
        if not field or field == "*" or parsed is None:
            return None

        value = _get_field_by_path(parsed, field)
        if value is None:
            return None

        try:
            num_value = float(value)
        except (TypeError, ValueError):
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Numeric range constraints",
                violation_detail=f"Field {field}={value!r} Not a numerical value",
            )

        if min_val is not None and num_value < float(min_val):
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Numeric range constraints",
                violation_detail=f"Field {field}={num_value} below minimum {min_val}",
            )
        if max_val is not None and num_value > float(max_val):
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Numeric range constraints",
                violation_detail=f"Field {field}={num_value} exceeds maximum value {max_val}",
            )
        return None

    def _check_schema_match(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """The entire parsed_dict matches the specified schema.

        P2.0 Implement a simplified version: only check whether schema_name is in the known schema registry,
        And try to verify it with the corresponding pydantic model. The schema verification itself has been performed by the manager s _validate_* done,
        This assertion is mainly used for"Explicitly record which execution violated which schema"statistical purposes.
        """
        schema_name = self._constraint_get(assertion, "schema_name")
        if not schema_name or parsed is None:
            return None

        # Delayed import avoids circular dependencies
        try:
            schema_model = self._get_schema_model(schema_name)
        except Exception as e:
            logger.warning(f"⚠️ [AssertionExecutor] schema {schema_name} Not available: {e}")
            return None

        if schema_model is None:
            logger.warning(f"⚠️ [AssertionExecutor] unknown schema: {schema_name}")
            return None

        try:
            schema_model(**parsed)
            return None  # Verification passed
        except Exception as e:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "schema Match check",
                violation_detail=f"no match schema {schema_name}: {e}",
            )

    def _check_regex_match(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Field regular matching"""
        field = self._constraint_get(assertion, "field") or assertion.target_field
        pattern = self._constraint_get(assertion, "pattern")
        if not pattern:
            return None

        # Value:field="*" Acts on raw_text, otherwise on parsed fields
        if field == "*" or not field:
            value = raw_text
        elif parsed is not None:
            value = _get_field_by_path(parsed, field)
        else:
            value = None

        if value is None:
            return None

        try:
            if not re.search(pattern, str(value)):
                return AssertionViolation(
                    assertion_id=assertion.assertion_id,
                    assertion_type=assertion.assertion_type,
                    target_agent=assertion.target_agent,
                    severity=assertion.severity,
                    description=assertion.description or "Regular match check",
                    violation_detail=f"Field {field} Value does not match regular {pattern!r}",
                )
        except re.error as e:
            logger.warning(f"⚠️ [AssertionExecutor] Regular expression is invalid {pattern!r}: {e}")
            return None
        return None

    def _check_section_required(
        self,
        assertion: AgentAssertion,
        raw_text: str,
        parsed: Optional[Dict[str, Any]],
    ) -> Optional[AssertionViolation]:
        """Required section check (applies to original text)"""
        sections = self._constraint_get(assertion, "sections") or []
        if not sections or not raw_text:
            return None

        missing = [s for s in sections if s and s not in raw_text]
        if missing:
            return AssertionViolation(
                assertion_id=assertion.assertion_id,
                assertion_type=assertion.assertion_type,
                target_agent=assertion.target_agent,
                severity=assertion.severity,
                description=assertion.description or "Required Chapter Check",
                violation_detail=f"missing chapter: {missing}",
            )
        return None

    # ==================== Helper methods ====================

    def _get_schema_model(self, schema_name: str):
        """Get pydantic schema model by name (lazy import avoids circular dependencies).

        Return None if the schema is unknown.
        """
        if schema_name == "RiskAssessmentOutput":
            from core.agents.adapters.risk_manager_v2 import RiskAssessmentOutput
            return RiskAssessmentOutput
        if schema_name == "ResearchManagerOutput":
            from core.agents.adapters.research_manager_v2 import ResearchManagerOutput
            return ResearchManagerOutput
        return None

    def _fire_and_forget_hit_count(self, assertion_ids: List[str]) -> None:
        """Asynchronous trigger hit count (fire-and-forget, does not block the main process)"""
        try:
            for assertion_id in assertion_ids:
                try:
                    agent_assertion_service.increment_hit_count_sync(assertion_id)
                except Exception as e:
                    logger.debug(f"hit_count Auto-increment failed (does not affect the main process): assertion_id={assertion_id}, error={e}")
        except Exception as e:
            logger.debug(f"fire-and-forget hit_count Abnormal: {e}")

    # assertion type -> handler Mapping (populated after class definition)
    _HANDLERS: Dict[AssertionType, Any] = {}


# Populate handler mapping (community version does not have agent_assertion model, AssertionType is not available → Skip padding;
# run_assertions_sync Raised in advance when the backend is unavailable, _HANDLERS will not be accessed)
try:
    AssertionExecutor._HANDLERS = {
        AssertionType.TERM_FORBIDDEN: AssertionExecutor._check_term_forbidden,
        AssertionType.FIELD_REQUIRED: AssertionExecutor._check_field_required,
        AssertionType.FIELD_ENUM: AssertionExecutor._check_field_enum,
        AssertionType.FIELD_RANGE: AssertionExecutor._check_field_range,
        AssertionType.SCHEMA_MATCH: AssertionExecutor._check_schema_match,
        AssertionType.REGEX_MATCH: AssertionExecutor._check_regex_match,
        AssertionType.SECTION_REQUIRED: AssertionExecutor._check_section_required,
    }
except NameError:  # Community edition path: AssertionType is undefined
    pass


# Global singleton
assertion_executor = AssertionExecutor()
