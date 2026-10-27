"""Business acceptance layer interface skeleton."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from core.llm import Message, UnifiedLLMClient

from .skill_spec import (
    BusinessRuleFailure,
    BusinessVerificationResult,
    ImplementationFactReport,
    SandboxResult,
    SkillSpec,
    ValidationCheck,
)
from .financial_schema_context import (
    build_schema_generated_checks,
    infer_financial_schema_profile,
    resolve_financial_schema_context,
)

logger = logging.getLogger(__name__)

# Business acceptance LLM judgment timeout (seconds)
BUSINESS_LLM_TIMEOUT_SECONDS = 120


class BusinessVerifier:
    """Business acceptor interface."""

    def verify(
        self,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> BusinessVerificationResult:
        raise NotImplementedError


class DefaultBusinessVerifier(BusinessVerifier):
    """Default business acceptor.

    Check with rules + LLM Judgment:
    - Rule checking: field existence, status code, all-zero detection (zero cost, quick interception of obvious errors)
    - LLM Judgment: data conflicts, business rationality (accurate judgment to avoid misjudgment leading to retry costs)
    """

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._llm_client = llm_client
        self._provider = provider
        self._model = model

    def _get_client(self) -> Optional[UnifiedLLMClient]:
        if self._llm_client is not None:
            return self._llm_client
        if self._provider:
            try:
                kwargs: Dict[str, Any] = {}
                if self._model:
                    kwargs["model"] = self._model
                self._llm_client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
            except Exception as exc:
                logger.warning(f"Business acceptance LLM client initialization failed: {exc}")
        return self._llm_client

    def verify(
        self,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> BusinessVerificationResult:
        result = BusinessVerificationResult(
            passed=bool(sandbox_result.success),
            business_score=10.0 if sandbox_result.success else 0.0,
            details={
                "verifier": self.__class__.__name__,
                "spec_category": spec.category,
            },
        )
        if not sandbox_result.success:
            result.failures.append(
                BusinessRuleFailure(
                    rule_id="sandbox_success",
                    message=sandbox_result.error or "Sandbox execution failed and business acceptance cannot be entered.",
                )
            )
            return result

        output = sandbox_result.output
        generated_checks = self._resolve_generated_checks(spec, fact_report)
        schema_context = self._resolve_schema_verification_context(spec)
        schema_checks = self._build_schema_generated_checks(schema_context)
        generated_checks.extend(schema_checks)
        generated_checks = self._dedupe_checks(generated_checks)
        result.details["generated_check_count"] = len(generated_checks)
        result.details["schema_generated_check_count"] = len(schema_checks)
        if schema_context:
            result.details["schema_verification"] = schema_context
        result.details["output_type"] = type(output).__name__ if output is not None else None
        result.details["executed_checks"] = []

        # 🔬 Log: Output all acceptance rules to facilitate tracking field name changes
        check_summary = []
        for c in generated_checks:
            check_summary.append(f"  {c.check_type}:{c.name} field={c.field or '-'} blocking={c.blocking}")
        logger.info(
            "🔬 [BusinessVerifier] Summary of acceptance rules(%d Article) | tool_id=%s:\n%s",
            len(generated_checks),
            spec.tool_id,
            "\n".join(check_summary),
        )

        for check in generated_checks:
            self._apply_check(result, output, check)

        # Numerical sanity checking: detecting obviously erroneous output
        self._apply_plausibility_checks(result, output, spec)

        # LLM Business acceptance: Use LLM to judge data contradictions and business rationality (accurate judgment, not relying on keywords/regulars)
        self._apply_llm_business_check(result, output, sandbox_result, spec, fact_report)

        if result.failures:
            result.passed = False
            result.business_score = min(result.business_score or 10.0, 3.0)
            result.details["blocking_failure_count"] = len(result.failures)
        elif result.warnings:
            result.passed = True
            result.business_score = min(result.business_score or 10.0, 8.0)
            result.details["warning_check_count"] = len(result.warnings)
        return result

    @staticmethod
    def _resolve_schema_verification_context(spec: SkillSpec) -> Optional[Dict[str, Any]]:
        return resolve_financial_schema_context(spec)

    @staticmethod
    def _infer_schema_profile(spec: SkillSpec) -> Optional[Dict[str, str]]:
        return infer_financial_schema_profile(spec)

    @staticmethod
    def _build_schema_generated_checks(schema_context: Optional[Dict[str, Any]]) -> List[ValidationCheck]:
        return build_schema_generated_checks(schema_context)

    @staticmethod
    def _dedupe_checks(checks: List[ValidationCheck]) -> List[ValidationCheck]:
        deduped: List[ValidationCheck] = []
        seen = set()
        for check in checks:
            key = (
                check.name or "",
                check.check_type or "",
                check.field or "",
                check.value_path or "",
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(check)
        return deduped

    @staticmethod
    def _resolve_generated_checks(
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport],
    ) -> List[ValidationCheck]:
        checks: List[ValidationCheck] = []
        raw_checks = list(spec.validation_checks or [])
        if fact_report and fact_report.validation_checks:
            existing_names = {check.name for check in raw_checks if check.name}
            # 🔧 spec is an authoritative source and its required_field check takes precedence over fact_report (reconnaissance results may have field name hallucinations)
            spec_has_required_fields = any(
                c.check_type == "required_field" for c in raw_checks
            )
            for check in fact_report.validation_checks:
                if check.name and check.name in existing_names:
                    continue
                # 🔧 If spec already has a required_field check, skip all required_fields in fact_report.
                #    Avoid conflicts between field names output by LLM reconnaissance and spec, causing acceptance rules to compete with each other.
                if spec_has_required_fields and check.check_type == "required_field":
                    logger.info(
                        "🔬 [_resolve_generated_checks] skip fact_report required_field: name=%s field=%s (spec Already required_field, subject to spec)",
                        check.name,
                        check.field,
                    )
                    continue
                raw_checks.append(check)

        logger.info(
            "🔬 [_resolve_generated_checks] spec_checks=%d fact_report_checks=%d total_raw=%d | tool_id=%s",
            len(spec.validation_checks or []),
            len(fact_report.validation_checks if fact_report else []),
            len(raw_checks),
            spec.tool_id,
        )

        for raw in raw_checks:
            normalized_type = DefaultBusinessVerifier._normalize_check_type(raw.check_type, raw.rule_level)
            rule_level = DefaultBusinessVerifier._default_rule_level(normalized_type, raw.rule_level)

            if normalized_type in ("business", "custom"):
                checks.append(
                    ValidationCheck(
                        name=raw.name,
                        description=raw.description,
                        required=False,
                        check_type="custom",
                        rule_level=rule_level,
                        blocking=False,
                        field=raw.field,
                        value_path=raw.value_path,
                        forbid_null=raw.forbid_null,
                        params=raw.params,
                    )
                )
                continue

            if normalized_type == "input_validation":
                checks.append(
                    ValidationCheck(
                        name=raw.name or "status_success",
                        description=raw.description or "输入与执行状态必须有效",
                        required=raw.required,
                        check_type="status_success",
                        rule_level=rule_level,
                        blocking=raw.blocking,
                        value_path="output",
                        forbid_null=False,
                        params=raw.params,
                    )
                )
                continue

            if normalized_type == "data_validation":
                if raw.field:
                    checks.append(
                        ValidationCheck(
                            name=raw.name or f"required_field:{raw.field}",
                            description=raw.description or f"关键数据字段 {raw.field} 不可缺失",
                            required=raw.required,
                            check_type="required_field",
                            rule_level=rule_level,
                            blocking=raw.blocking,
                            field=raw.field,
                            value_path=raw.value_path or "data",
                            forbid_null=True,
                            params=raw.params,
                        )
                    )
                elif spec.expected_output.fields:
                    for field_name in spec.expected_output.fields:
                        checks.append(
                            ValidationCheck(
                                name=f"{raw.name or 'data_validation'}:{field_name}",
                                description=raw.description or f"关键输出字段 {field_name} 不可缺失",
                                required=raw.required,
                                check_type="required_field",
                                rule_level=rule_level,
                                blocking=raw.blocking,
                                field=field_name,
                                value_path=raw.value_path or "data",
                                forbid_null=True,
                                params=raw.params,
                            )
                        )
                else:
                    checks.append(
                        ValidationCheck(
                            name=raw.name or "required_non_empty_payload",
                            description=raw.description or "A non-empty data payload must be returned on successful output.",
                            required=raw.required,
                            check_type="required_non_empty_payload",
                            rule_level=rule_level,
                            blocking=raw.blocking,
                            value_path=raw.value_path or "data",
                            forbid_null=True,
                            params=raw.params,
                        )
                    )
                continue

            checks.append(
                ValidationCheck(
                    name=raw.name,
                    description=raw.description,
                    required=raw.required,
                    check_type=normalized_type,
                    rule_level=rule_level,
                    blocking=raw.blocking,
                    field=raw.field,
                    value_path=raw.value_path,
                    forbid_null=raw.forbid_null,
                    params=raw.params,
                )
            )

        if not any(check.check_type == "status_success" for check in checks):
            checks.insert(
                0,
                ValidationCheck(
                    name="status_success",
                    description="The output status must be success/ok",
                    check_type="status_success",
                    rule_level="output",
                    blocking=True,
                    value_path="output",
                    forbid_null=False,
                )
            )

        if not any(check.check_type in ("required_field", "required_non_empty_payload") for check in checks):
            if spec.expected_output.fields:
                for field_name in spec.expected_output.fields:
                    checks.append(
                        ValidationCheck(
                            name=f"required_field:{field_name}",
                            description=f"成功输出时必须包含字段 {field_name}",
                            check_type="required_field",
                            rule_level="data",
                            blocking=True,
                            field=field_name,
                            value_path="data",
                            forbid_null=True,
                        )
                    )
            else:
                checks.append(
                    ValidationCheck(
                        name="required_non_empty_payload",
                        description="A non-empty data payload must be returned on successful output.",
                        check_type="required_non_empty_payload",
                        rule_level="data",
                        blocking=True,
                        value_path="data",
                        forbid_null=True,
                    )
                )
        return checks

    def _apply_check(
        self,
        result: BusinessVerificationResult,
        output: Any,
        check: ValidationCheck,
    ) -> None:
        result.details.setdefault("executed_checks", []).append(
            {
                "name": check.name,
                "check_type": check.check_type,
                "rule_level": check.rule_level,
                "blocking": check.blocking,
            }
        )

        if check.check_type == "status_success":
            status = None
            if isinstance(output, dict):
                status = output.get("status", "success")
            elif isinstance(output, list):
                # list[dict] output(expected_output.type="list[dict]") There is no status field contract,
                # The successful execution of the sandbox is regarded as a successful state; previously, the list was mistakenly judged as a failure, resulting in the correct implementation being accidentally killed.
                status = "success"
            if not isinstance(status, str) or status.lower() not in ("success", "ok"):
                self._record_issue(
                    result,
                    check,
                    check.description or "The output status must be success/ok",
                )
            return

        if check.check_type == "required_non_empty_payload":
            target = self._resolve_target(output, check.value_path)
            if target in (None, "", [], {}):
                self._record_issue(
                    result,
                    check,
                    check.description or "A non-empty payload must be returned on successful output.",
                )
            return

        if check.check_type == "required_field":
            sample = self._resolve_sample(self._resolve_target(output, check.value_path))
            field_name = check.field or check.name.split(":", 1)[-1]
            if not isinstance(sample, dict):
                self._record_issue(
                    result,
                    check,
                    check.description or f"输出中缺少可检查字段 {field_name} 的结构化对象",
                )
                return
            exists, value = self._resolve_field_value(sample, field_name)
            if not exists:
                self._record_issue(
                    result,
                    check,
                    check.description or f"成功输出时必须包含字段 {field_name}",
                )
                return
            if check.forbid_null and value is None:
                self._record_issue(
                    result,
                    check,
                    check.description or f"成功输出时字段 {field_name} 不可为空",
                )
            return

        if check.check_type == "schema_condition":
            sample = self._resolve_sample(self._resolve_target(output, check.value_path))
            evaluation = self._evaluate_schema_condition(
                check.params.get("condition_expr") or {},
                sample,
            )
            if evaluation["passed"]:
                return

            if evaluation["missing_data"] and check.params.get("fallback_to_applicability_check"):
                applicability_check = sample.get("applicability_check") if isinstance(sample, dict) else None
                if isinstance(applicability_check, dict):
                    passed = applicability_check.get("passed")
                    if isinstance(passed, bool):
                        if passed:
                            return
                        self._record_issue(
                            result,
                            check,
                            check.description or "适用性规则校验未通过",
                        )
                        return

            message = check.description or "Schema applicability rule validation failed"
            if evaluation["message"]:
                message = f"{message} ({evaluation['message']})"
            if check.params.get("warning_only"):
                message = f"建议性规则未满足: {message}"
            self._record_issue(result, check, message)
            return

        if check.required:
            result.details.setdefault("unsupported_rule_types", []).append(check.check_type)
            self._record_issue(
                result,
                check,
                f"Unsupported business acceptance rule type: {check.check_type}",
            )

    @staticmethod
    def _default_rule_level(check_type: str, current_level: str = "") -> str:
        if check_type == "input_validation" and current_level in ("", "data"):
            return "input"
        if check_type == "status_success" and current_level in ("", "data"):
            return "output"
        if current_level:
            return current_level
        mapping = {
            "input_validation": "input",
            "status_success": "output",
            "required_field": "data",
            "required_non_empty_payload": "data",
            "data_validation": "data",
            "schema_condition": "method",
            "custom": "business",
        }
        return mapping.get(check_type, "business")

    @staticmethod
    def _normalize_check_type(check_type: str, rule_level: str = "") -> str:
        normalized = (check_type or "").strip().lower()
        level = (rule_level or "").strip().lower()

        if normalized in (
            "required_field",
            "required_non_empty_payload",
            "status_success",
            "input_validation",
            "data_validation",
            "schema_condition",
        ):
            return normalized
        if normalized in ("input", "input_check"):
            return "input_validation"
        if normalized in ("output", "output_check", "status"):
            return "status_success"
        if normalized in ("data", "data_check"):
            return "data_validation"
        if normalized in ("business", "business_check"):
            return "custom"
        if level == "input":
            return "input_validation"
        if level == "output":
            return "status_success"
        if level == "data":
            return "data_validation"
        if level == "business":
            return "custom"
        return normalized or "custom"

    @staticmethod
    def _record_issue(
        result: BusinessVerificationResult,
        check: ValidationCheck,
        message: str,
    ) -> None:
        if check.blocking and check.required:
            result.failures.append(
                BusinessRuleFailure(
                    rule_id=check.name or check.check_type,
                    message=message,
                    severity="error",
                )
            )
            return
        result.warnings.append(message)

    @classmethod
    def _evaluate_schema_condition(cls, condition_expr: Dict[str, Any], sample: Any) -> Dict[str, Any]:
        if not isinstance(condition_expr, dict):
            return {"passed": False, "missing_data": True, "message": "invalid condition expression"}

        op = str(condition_expr.get("op") or "").strip().lower()
        if not op:
            return {"passed": False, "missing_data": True, "message": "missing op"}

        if op == "field_exists":
            exists, _ = cls._resolve_field_value(sample, str(condition_expr.get("field") or ""))
            return {"passed": exists, "missing_data": not exists, "message": "field missing" if not exists else ""}

        if op in ("field_gt", "field_gte", "field_lt", "field_lte"):
            exists, value = cls._resolve_field_value(sample, str(condition_expr.get("field") or ""))
            if not exists:
                return {"passed": False, "missing_data": True, "message": "field missing"}
            try:
                numeric_value = float(value)
                threshold = float(condition_expr.get("value"))
            except (TypeError, ValueError):
                return {"passed": False, "missing_data": True, "message": "numeric comparison unavailable"}
            passed = {
                "field_gt": numeric_value > threshold,
                "field_gte": numeric_value >= threshold,
                "field_lt": numeric_value < threshold,
                "field_lte": numeric_value <= threshold,
            }[op]
            return {
                "passed": passed,
                "missing_data": False,
                "message": f"value={numeric_value}, expected {op} {threshold}" if not passed else "",
            }

        if op in ("industry_in", "industry_not_in"):
            exists, value = cls._resolve_field_value(sample, str(condition_expr.get("field") or ""))
            if not exists:
                return {"passed": False, "missing_data": True, "message": "industry field missing"}
            choices = condition_expr.get("value") or []
            if not isinstance(choices, list):
                choices = [choices]
            normalized_choices = {str(item).strip() for item in choices}
            current = str(value).strip()
            passed = current in normalized_choices
            if op == "industry_not_in":
                passed = not passed
            return {
                "passed": passed,
                "missing_data": False,
                "message": f"industry={current}" if not passed else "",
            }

        if op in ("all_of", "any_of"):
            conditions = condition_expr.get("conditions") or []
            if not isinstance(conditions, list) or not conditions:
                return {"passed": False, "missing_data": True, "message": "conditions missing"}
            results = [cls._evaluate_schema_condition(item, sample) for item in conditions]
            passed = all(item["passed"] for item in results) if op == "all_of" else any(item["passed"] for item in results)
            missing_data = any(item["missing_data"] for item in results)
            messages = [item["message"] for item in results if item.get("message")]
            return {"passed": passed, "missing_data": missing_data and not passed, "message": "; ".join(messages)}

        if op == "not":
            nested = cls._evaluate_schema_condition(condition_expr.get("condition") or {}, sample)
            return {
                "passed": not nested["passed"],
                "missing_data": nested["missing_data"],
                "message": nested.get("message", ""),
            }

        return {"passed": False, "missing_data": True, "message": f"unsupported op: {op}"}

    @staticmethod
    def _resolve_field_value(sample: dict, field_name: str) -> tuple[bool, Any]:
        if isinstance(sample, dict) and field_name in sample:
            return True, sample.get(field_name)
        current: Any = sample
        for part in (field_name or "").split("."):
            key = part.strip()
            if not key:
                continue
            if not isinstance(current, dict) or key not in current:
                return False, None
            current = current.get(key)
        return True, current

    @staticmethod
    def _resolve_target(output: Any, value_path: str) -> Any:
        if value_path == "output":
            return output
        if isinstance(output, dict):
            nested = output.get(value_path)
            if nested is not None:
                return nested
            # Fallback: If there is no nested key named value_path in output,
            # then treat output itself as the target (compatible with flat output structures).
            return output
        if isinstance(output, list):
            # list[dict] Output: The field check is against the record itself, and the list returned is _resolve_sample
            # Check the first record; previously, list directly returned None, causing all field checks to fail misjudged.
            return output
        return None

    @staticmethod
    def _resolve_sample(target: Any) -> Any:
        if isinstance(target, list):
            return target[0] if target else None
        return target

    @staticmethod
    def _apply_plausibility_checks(
        result: BusinessVerificationResult,
        output: Any,
        spec: SkillSpec,
    ) -> None:
        """Numerical plausibility checking: detecting obviously erroneous results (such as all-zero data)"""
        if not isinstance(output, dict):
            return

        def _collect_numeric_values(obj: Any, path: str = "") -> Dict[str, float]:
            """Recursively collect all numeric fields and their paths.

            Skip raw_data / raw raw echo fields: they are the complete raw return from the external interface
             (Traceability purposes), there are a large number of constant zero noise fields that have nothing to do with the business (such as the list of car emperors)
            score/descender_price) and should not be involved in judging the rationality of business values.
            """
            values: Dict[str, float] = {}
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if str(k).lower() in ("raw_data", "raw"):
                        continue
                    full_path = f"{path}.{k}" if path else k
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        values[full_path] = float(v)
                    elif isinstance(v, dict):
                        values.update(_collect_numeric_values(v, full_path))
                    elif isinstance(v, list) and v:
                        # Check each element in the list
                        for i, item in enumerate(v):
                            if isinstance(item, dict):
                                values.update(_collect_numeric_values(item, f"{full_path}[{i}]"))
            return values

        numeric_fields = _collect_numeric_values(output)
        if not numeric_fields:
            return  # No numeric fields, skip

        # Check: More than 3 key numeric fields are all 0
        zero_fields = [k for k, v in numeric_fields.items() if v == 0.0]
        total_fields = len(numeric_fields)

        if total_fields >= 3 and len(zero_fields) >= total_fields * 0.7:
            # More than 70% of the numeric fields are 0, which is likely to be a calculation logic error.
            sample = list(zero_fields)[:5]
            msg = (
                f"数值合理性失败：{len(zero_fields)}/{total_fields} 个数值字段为 0 "
                f" (Such as {', '.join(sample)}) , It may be a calculation logic error rather than real data"
            )
            result.failures.append(
                BusinessRuleFailure(
                    rule_id="all_zero_values",
                    message=msg,
                    severity="error",
                )
            )
            result.details["zero_value_fields"] = len(zero_fields)
            result.details["total_numeric_fields"] = total_fields
            return

        # Check: Nested fields are all zeros (e.g. every value in the trend/series list is 0)
        list_zero_count = 0
        for k, v in numeric_fields.items():
            if "[0]" in k or "[1]" in k or "[2]" in k:
                if v == 0.0:
                    list_zero_count += 1

        if list_zero_count >= 3 and total_fields >= 5:
            msg = (
                f"Numeric rationality failed: all data in the list are 0 (total {list_zero_count} zero value),"
                "Trend/sequence data cannot be all 0, and the data acquisition or calculation logic is incorrect."
            )
            result.failures.append(
                BusinessRuleFailure(
                    rule_id="trend_list_all_zeros",
                    message=msg,
                    severity="error",
                )
            )
            result.details["trend_zero_count"] = list_zero_count

    def _apply_llm_business_check(
        self,
        result: BusinessVerificationResult,
        output: Any,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport],
    ) -> None:
        """LLM Business acceptance — Simple inline prompt mode, all evidence is passed in at once"""
        client = self._get_client()
        if client is None:
            logger.warning("Business acceptance LLM client is unavailable, skip LLM business acceptance")
            return

        logger.info(f"🤖 [BusinessVerifier] LLM Business acceptance starts | tool_id={spec.tool_id}")

        test_symbol = spec.test_input.get("symbol", "") or spec.test_input.get("code", "")
        test_name = spec.test_input.get("name", "") or spec.test_input.get("display_name", "")

        # Prepare output summary
        try:
            output_str = json.dumps(output, ensure_ascii=False, indent=2, default=str)[:4000]
        except Exception:
            output_str = str(output)[:4000]

        # Build helper manifest
        helpers_block = "（无 helper）"
        if fact_report and fact_report.available_helpers:
            lines = []
            for h in fact_report.available_helpers:
                ds_tag = getattr(h, 'data_source_handling', 'self_contained') or 'self_contained'
                sig = getattr(h, 'signature', '') or '(无签名)'
                lines.append(f"  {h.name}: {sig} [{ds_tag}]")
            if lines:
                helpers_block = "\n".join(lines)

        # Build log summary (take last 60 lines)
        log_block = "（无日志）"
        if sandbox_result.stdout:
            log_lines = sandbox_result.stdout.strip().split("\n")
            log_block = "\n".join(log_lines[-60:])

        # Build inline user message
        # ⚠️ The current system date must be injected: LLM pair"current time"The perception comes from the training data (often lagged several months),
        # Based on this, the completed month was misjudged as"future months", As a result, the correct implementation was repeatedly mistakenly killed.
        from datetime import datetime as _dt
        current_date = _dt.now().strftime("%Y-%m-%d")
        user_msg = (
            f"当前系统日期: {current_date}（判断任何时间合理性问题时必须以此为准，"
            f"It is strictly prohibited to use the time in your training memory)\n"
            f"Test target: {test_symbol} {test_name}\n"
            f"Skill Function: {spec.description}\n\n"
            f" [Sandbox execution results]\n"
            f"  success: {sandbox_result.success}\n"
            f"  error: {sandbox_result.error or 'None'}\n"
            f"  Output summary: {output_str}\n\n"
            f" [Sandbox log (last 60 lines)]\n{log_block}\n\n"
            f" [Confirmed available helper functions]\n{helpers_block}\n\n"
            f"Judgment points:\n"
            f"1. Does the data in the logs contradict the output?(helper There is data but the output is empty → has_contradiction=true)\n"
            f"2. Is the output business reasonable?(No pledge data for blue chip stocks → is_business_valid=true)\n"
            f"3. success=True It means that the code has been executed successfully and the function must exist.\n"
            f"4. Time rationality is based on the [current system date] at the top: the query cycle is earlier than or equal to this date"
            f"All are legal historical/current cycles and shall not be judged as'future months'. \n"
            f"5. 🚨 Cross-helper consistency check: if a Skill calls multiple helpers,\n"
            f"   Check if their returns contradict each other. For example:\n"
            f"   - a helper says'No pledge' (status=no_pledge) , Another returns a list of pledged shareholders → has_contradiction=true, severity=critical\n"
            f"   - One helper returns empty trend series, the other returns non-empty data → has_contradiction=true\n"
            f"   - Two helpers give different values for the same indicator → has_contradiction=true\n\n"
            f"Output format, only output the following, no other content:\n"
            f"<verdict>\n"
            f'{{"has_contradiction": true/false, "is_business_valid": true/false, '
            f'"severity": "none/minor/major/critical", "issue": "a word", "suggestion": "Repair suggestions"}}\n'
            f"</verdict>"
        )

        try:
            import queue
            import threading

            result_queue: "queue.Queue[tuple[str, Any]]" = queue.Queue(maxsize=1)

            def _worker() -> None:
                try:
                    messages = [
                        Message(role="system", content="You are an expert in financial data auditing. Determine whether there are data conflicts or business irrationality in the execution results of the Skill tool. Output strictly according to the format <verdict> JSON. "),
                        Message(role="user", content=user_msg),
                    ]
                    response = client.chat(messages, temperature=0.0, max_tokens=2048)
                    result_queue.put(("ok", response.content or ""))
                except Exception as exc:
                    result_queue.put(("error", exc))

            worker = threading.Thread(
                target=_worker, name=f"biz-verify-{spec.tool_id}", daemon=True
            )
            worker.start()
            worker.join(BUSINESS_LLM_TIMEOUT_SECONDS)

            if worker.is_alive():
                logger.warning(
                    f"Business acceptance LLM judgment timeout ({BUSINESS_LLM_TIMEOUT_SECONDS}s) , skip | tool_id={spec.tool_id}"
                )
                return

            status, payload = result_queue.get_nowait()
            if status == "error":
                raise payload
            raw = str(payload)

            if not raw:
                logger.warning("Business acceptance LLM returns empty content and skips")
                return

            logger.info(f"📥 [BusinessVerifier] LLM output: {raw[:500]}")

            # Parse JSON: Prioritize from <verdict> Extract from tags
            import re
            verdict_match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", raw, re.DOTALL)
            if verdict_match:
                json_str = verdict_match.group(1).strip()
            else:
                json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
                json_str = json_match.group() if json_match else ""

            if not json_str:
                logger.warning(f"Business Acceptance LLM output cannot be parsed as JSON: {raw[:300]}")
                return

            try:
                verdict = json.loads(json_str)
            except json.JSONDecodeError as je:
                logger.warning(f"Business acceptance LLM JSON parsing failed: {je} | json_str={json_str[:200]}")
                return

            has_contradiction = bool(verdict.get("has_contradiction", False))
            is_business_valid = bool(verdict.get("is_business_valid", True))
            severity = str(verdict.get("severity", "none")).lower()
            issue = str(verdict.get("issue", "")).strip()
            suggestion = str(verdict.get("suggestion", "")).strip()

            result.details["llm_business_check"] = {
                "has_contradiction": has_contradiction,
                "is_business_valid": is_business_valid,
                "severity": severity,
                "issue": issue,
                "suggestion": suggestion,
            }

            # Data conflict → Directly judged as failure (blocked)
            if has_contradiction:
                msg = f"Data conflicts (LLM judgment): {issue}"
                if suggestion and suggestion != "无":
                    msg += f" | 修复建议: {suggestion}"
                result.failures.append(
                    BusinessRuleFailure(
                        rule_id="llm_data_contradiction",
                        message=msg,
                        severity="error",
                    )
                )
                logger.warning(f"🚨 [BusinessVerifier] LLM Data inconsistency detected: {issue}")
            elif not is_business_valid and severity in ("major", "critical"):
                msg = f"The business is unreasonable (LLM judgment): {issue}"
                if suggestion and suggestion != "无":
                    msg += f" | 修复建议: {suggestion}"
                result.failures.append(
                    BusinessRuleFailure(
                        rule_id="llm_business_invalid",
                        message=msg,
                        severity="error",
                    )
                )
                logger.warning(f"🚨 [BusinessVerifier] LLM Determining the business to be unreasonable: {issue}")
            elif severity == "minor":
                result.warnings.append(f"LLM 业务验收建议: {issue}")
                logger.info(f"ℹ️ [BusinessVerifier] LLM Found small problems: {issue}")
            else:
                logger.info(f"✅ [BusinessVerifier] LLM Business acceptance passed: {issue}")

        except Exception as exc:
            logger.warning(f"Business acceptance LLM judgment abnormality: {exc}", exc_info=True)


class ValuationBusinessVerifier(DefaultBusinessVerifier):
    """The valuation class acceptor type name is retained and no hard-coded rules are currently built in."""

    def verify(
        self,
        sandbox_result: SandboxResult,
        spec: SkillSpec,
        fact_report: Optional[ImplementationFactReport] = None,
    ) -> BusinessVerificationResult:
        result = super().verify(sandbox_result, spec, fact_report)
        result.details["verifier"] = self.__class__.__name__
        result.details["rule_family"] = "valuation"
        return result


class BusinessVerifierRegistry:
    """Select the business acceptor by skill type."""

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._llm_client = llm_client
        self._provider = provider
        self._model = model

    def resolve(self, spec: SkillSpec) -> BusinessVerifier:
        return DefaultBusinessVerifier(
            llm_client=self._llm_client,
            provider=self._provider,
            model=self._model,
        )

    def list_rule_families(self) -> List[str]:
        return ["default"]