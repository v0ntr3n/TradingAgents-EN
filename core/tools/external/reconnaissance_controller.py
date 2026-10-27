"""Skill Generate front-end reconnaissance layer — LLM drive + Tool calling mode.

The reconnaissance layer runs before code generation and explores autonomously through LLM function-calling:
- Fields and coverage of database collections
- skill_runtime Expose the helper s signature and purpose
- Sample data for specified stocks

Outputs a structured ImplementationFactReport for consumption by CodeGenerator.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from functools import wraps
from typing import Any, Dict, List, Optional

from .recon_tools import RECON_TOOLS
from .requirement_analyzer import RequirementAnalyzer
from .data_contracts import build_data_contract_doc_for_skill
from .financial_schema_context import build_schema_generated_checks, resolve_financial_schema_context
from core.skill_runtime import build_factor_catalog_prompt_context
from .skill_spec import (
    ImplementationFact,
    ImplementationFactReport,
    ImplementationHelper,
    ImplementationIssue,
    ReconToolTrace,
    SkillSpec,
    ValidationCheck,
)

logger = logging.getLogger(__name__)

# LLM Reconnaissance maximum tool call rounds
# Adjusted from 10 to 6: rule_report already provides helpers through vector search, LLM only needs to add verification,
# No need to explore all collections/modules from scratch. Too many rounds will slow down the generation process and provide diminishing returns.
MAX_RECON_TOOL_ROUNDS = 6


class ReconnaissanceController:
    """Front reconnaissance layer interface."""

    def analyze(self, spec: SkillSpec) -> ImplementationFactReport:
        raise NotImplementedError


class DefaultReconnaissanceController(ReconnaissanceController):
    """LLM Driver s reconnaissance layer implementation.

    Phase 1 (Rule baseline): Use RequirementAnalyzer to do static inference and generate initial facts.
    Phase 2 (LLM Explore): Pass UnifiedLLMClient + Tool call, let LLM decide independently
    See which collection schemas, which helper descriptions are called, which field coverage is checked.
    The LLM output is finally parsed into an ImplementationFactReport.

    If the LLM client is unavailable or the call fails, it automatically degrades to rule-only mode.
    """

    def __init__(
        self,
        llm_client=None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        analyzer: Optional[RequirementAnalyzer] = None,
    ):
        self._llm_client = llm_client
        self._provider = provider
        self._model = model
        self._analyzer = analyzer or RequirementAnalyzer()

    def _get_client(self):
        """Get or delay creation of LLM client."""
        if self._llm_client is None:
            try:
                from core.llm import UnifiedLLMClient
                kwargs = {}
                if self._model:
                    kwargs["model"] = self._model
                self._llm_client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
            except Exception as exc:
                logger.warning("⚠️ Recon layer cannot create LLM client and will be downgraded to rules mode: %s", exc)
                return None
        return self._llm_client

    def analyze(self, spec: SkillSpec, capability_hits: list = None) -> ImplementationFactReport:
        # Phase 1: Rule baseline (fast, zero cost)
        rule_report = self._rule_based_analyze(spec, capability_hits)

        #  [Layered strategy] Determine whether to enable or not based on the number of helpers Phase 2
        # - 1-2 A helper (such as staking): directly verify the signature, skipping LLM exploration
        # - 3+ Helpers (such as valuation, cash flow): Enter Phase 2, but only screening is done, and exploration of new tools is not allowed
        helper_count = len(rule_report.available_helpers)
        if helper_count <= 2:
            helper_names = [h.name for h in rule_report.available_helpers]
            logger.info(
                f"\n{'='*80}\n"
                f"✅ [Reconnaissance layer optimization] Phase 1 Found {helper_count} helper, skip directly Phase 2\n"
                f"   discovered helper: {', '.join(helper_names)}\n"
                f"   Confidence: {rule_report.confidence:.2f}\n"
                f"   Reason: A small number of helper scenarios do not require LLM filtering\n"
                f"{'='*80}"
            )
            return rule_report

        # Phase 2: LLM driver filter (only if helper >= 3 enabled)
        client = self._get_client()
        if client is None:
            logger.info("🧭 Recon layer downgraded to rules-only mode (no LLM client)")
            return rule_report

        logger.info(
            f"\n{'='*80}\n"
            f"🔄 [Reconnaissance level] Phase 1 Found {helper_count} candidate helpers, start Phase 2 LLM screening\n"
            f"   candidate list: {', '.join([h.name for h in rule_report.available_helpers])}\n"
            f"   Task: Filter the most relevant 3-4 from known candidates without exploring new tools\n"
            f"{'='*80}"
        )

        try:
            llm_report = self._llm_driven_analyze(
                client, spec, rule_report,
                has_many_helpers=True  # Multiple helper scenarios: only filtering
            )
            return llm_report
        except Exception as exc:
            logger.warning("⚠️ LLM Reconnaissance failed, downgraded to rules mode: %s", exc)
            return rule_report

    @staticmethod
    def _extract_probe_symbol(spec: SkillSpec) -> Optional[str]:
        test_input = spec.test_input or {}
        symbol_candidates = [
            test_input.get("symbol"),
            test_input.get("stock_code"),
            test_input.get("code"),
            test_input.get("ticker"),
        ]
        for item in symbol_candidates:
            normalized = DefaultReconnaissanceController._normalize_symbol(item)
            if normalized:
                return normalized
        for parameter in spec.parameters:
            normalized = DefaultReconnaissanceController._normalize_symbol(parameter.default)
            if normalized:
                return normalized
        return None

    @staticmethod
    def _normalize_symbol(value: Any) -> Optional[str]:
        text = str(value or "").strip()
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) == 6:
            return digits
        return None

    @staticmethod
    def _build_strategy(spec: SkillSpec, recommendations: dict) -> str:
        local_collections = recommendations.get("stock_collections") or []
        external_sources = recommendations.get("external_sources") or []
        strategy = ["Prioritize using the skill_runtime public interface and local synchronized data"]
        if local_collections:
            strategy.append(f"优先关注本地集合: {', '.join(local_collections[:3])}")
        if external_sources:
            strategy.append(f"External sources are used only as supplementary reconnaissance evidence: {', '.join(external_sources[:3])}")
        if "估值" in spec.description or any(k in spec.description.lower() for k in ("valuation", "peg", "pb", "pe", "dcf")):
            strategy.append("First confirm the price, financial caliber and growth path, and then solidify the valuation formula")
        return "；".join(strategy)

    # ==================== Requirement type diversion (improvement point 1) ====================

    @staticmethod
    def _classify_requirement_mode(spec: SkillSpec) -> str:
        """Identify the requirement type: external_api (external API integration) / local_data (local data reuse, default).

        The decision logic is unified and implemented in requirement_analyzer.classify_requirement_mode.
        The method shell is reserved here for calling within the reconnaissance layer and existing tests.
        """
        from .requirement_analyzer import classify_requirement_mode

        return classify_requirement_mode(spec)

    @staticmethod
    def _build_external_api_strategy(spec: SkillSpec, unknown_data_source: str = "") -> str:
        """external_api Implementation strategies for patterns."""
        source_name = unknown_data_source or (getattr(spec, "data_source", "") or "用户指定来源")
        return (
            f"This requirement is for external HTTP API integration (data source: {source_name}, Does not belong to the system s local stock data system)."
            "The implementation is mainly to directly call the external interface:requests/httpx + Legal request header (UA/Referer)+ Timeout and failure downgrade;"
            "Do not use local stock collections or reuse stock helpers as data sources."
            "Interface specifications (URL, request method, parameters, authentication, return fields) must be subject to the information confirmed by the user."
            "Do not make up interface details and field names without confirmation."
        )

    # ==================== Acceptance field consistency check (improvement point 3) ====================

    @staticmethod
    def _normalize_field_token(name: str) -> str:
        return "".join(ch for ch in str(name or "").lower() if ch.isalnum())

    def _validate_expected_field_coverage(
        self,
        spec: SkillSpec,
        report: ImplementationFactReport,
        requirement_mode: str,
    ) -> None:
        """Verify that expected_output.fields is consistent with the capabilities of the hit asset.

        - local_data Mode: Fields should be able to be produced by helper return fields/local collection sample fields,
          When the coverage is too low, the confidence level is lowered and clarification is prompted (to prevent speculative fields from being created).
        - external_api Mode: The field comes from the actual response of the external interface, and no local coverage verification is performed.
          Prompt only"Fields must be based on the actual response of the interface. Levels where the interface does not exist must not be declared.". 
        """
        expected_output = getattr(spec, "expected_output", None)
        expected = [str(f).strip() for f in (getattr(expected_output, "fields", None) or []) if str(f or "").strip()]
        if not expected:
            return

        if requirement_mode == "external_api":
            report.notes.append(
                "⚠️ The acceptance fields must be based on the actual response of the external interface: expected_output.fields must not contain fields not provided by the interface"
                " (For example, when the interface returns by car series level, model_id/model_name/manufacturer_id, etc. should not be declared."
                "Hierarchical fields that do not exist in the interface); the field list needs to be checked with the user when the specifications are confirmed."
            )
            return

        # local_data Mode: Collect the field pool that can be produced by hit assets
        pool: set = set()
        for fields in (report.sample_fields or {}).values():
            pool.update(self._normalize_field_token(f) for f in fields or [])
        for helper in report.available_helpers:
            for fname in self._analyzer._extract_return_field_names(helper.description or ""):
                pool.add(self._normalize_field_token(fname))
        for fact in report.schema_facts:
            if fact.field:
                pool.add(self._normalize_field_token(fact.field))
        if not pool:
            return  # If there is no asset field information, no forced judgment will be made.

        missing = [f for f in expected if self._normalize_field_token(f) not in pool]
        coverage = 1 - len(missing) / len(expected)
        if missing and coverage < 0.5:
            report.notes.append(
                f"⚠️ 验收字段覆盖不足（{len(expected) - len(missing)}/{len(expected)}）："
                f"{', '.join(missing[:8])} Cannot be produced by the currently hit helper/local collection."
                "These fields need to be provided by external data sources or self-calculation. It is recommended to clarify the source of the fields to the user before confirming the specifications."
            )
            report.confidence = min(report.confidence, 0.45)

    @staticmethod
    def _infer_helpers(spec: SkillSpec) -> list[ImplementationHelper]:
        normalized = f"{spec.display_name} {spec.description} {spec.category}".lower()
        helpers: list[ImplementationHelper] = []
        if any(k in normalized for k in ("valuation", "估值", "peg", "pb", "pe", "ps", "dcf")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.data_access",
                    name="get_stock_valuation_context",
                    signature="symbol: str, *, lookback_days: int = 90",
                    description="The standard input entrance for valuation skills, which can obtain current prices, valuation indicators and financial data at one time",
                    reason="The standard input entrance for valuation skills, which can obtain current prices, valuation indicators and financial data at one time",
                    data_source_handling="local_only",
                )
            )
        if any(k in normalized for k in ("行业", "peer", "relative", "同行", "pb", "pe", "ps")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.data_access",
                    name="summarize_industry_valuation",
                    signature="industry: str, *, top_n: int = 10",
                    description="Relative valuations and industry statistics prioritize reusing existing industry valuation summaries. helper",
                    reason="Relative valuations and industry statistics prioritize reusing existing industry valuation summaries. helper",
                    data_source_handling="local_only",
                )
            )
        # Moat/profit stability/long-term trend skills are prioritized for reuse standard_financial_apis
        if any(k in normalized for k in ("moat", "护城河", "稳定性", "stability", "质量", "quality", "长期", "annual_series", "年报序列")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.standard_financial_apis",
                    name="get_historical_financial_annual_series",
                    signature="symbol: str, years: int = 10, source: str = None",
                    description="Return the last N years of annual report series with one click (revenue/net_profit/roe/gross_margin/operating_cashflow, etc.)",
                    reason="The preferred entry point for long-term financial ledgers and 5-10 year trend analysis to avoid manually traversing multiple periods of data.",
                    data_source_handling="local_only",
                )
            )
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.standard_financial_apis",
                    name="get_profitability_stability_metrics",
                    signature="symbol: str, years: int = 10, source: str = None",
                    description="Calculate the mean, volatility, and coefficient of variation of revenue/net profit/ROE/gross profit margin based on the annual report sequence",
                    reason="Priority functions for earnings stability and moat financial evidence analysis to avoid double counting of statistical indicators",
                    data_source_handling="local_only",
                )
            )
        if any(k in normalized for k in ("现金流", "cashflow", "自由现金流", "fcf", "ocf", "利润含金量")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.standard_financial_apis",
                    name="get_cashflow_quality_trend",
                    signature="symbol: str, years: int = 10, source: str = None",
                    description="Returns annual trend and statistical summary of OCF/Net Profit, FCF/Net Profit, OCF Margin, FCF Margin",
                    reason="Priority functions for cash flow quality and profit content analysis",
                    data_source_handling="local_only",
                )
            )
        if any(k in normalized for k in ("分位", "percentile", "估值分位", "历史估值", "pe_ttm", "pb")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.standard_financial_apis",
                    name="get_historical_valuation_percentile",
                    signature="symbol: str, metrics: list = None, lookback_years: int = 5, as_of_date: str = None",
                    description="Structured returns the historical quantile, current value, and median of pe_ttm/pb/ps_ttm/pcf_ttm",
                    reason="Priority function for historical valuation quantile analysis, replacing text quantile output",
                    data_source_handling="self_contained",
                )
            )
        # Equity pledge/Major shareholder pledge/Pledge risk
        if any(k in normalized for k in ("质押", "pledge", "股权质押", "大股东质押", "爆仓", "平仓线")):
            helpers.append(
                ImplementationHelper(
                    module="core.skill_runtime.standard_financial_apis",
                    name="get_pledge_risk_profile",
                    signature="symbol: str, source: str = None",
                    description="Return to equity pledge risk portrait: total pledge ratio, unreleased pledge size, top pledge shareholders, recent pledge events, risk level(low/medium/medium_high/high/none)",
                    reason="The priority function for equity pledge risk snapshot analysis, automatically obtains data from Tushare/akshare without manually calling external interfaces",
                    data_source_handling="self_contained",
                )
            )
            if any(k in normalized for k in ("趋势", "历史", "trend", "historical", "年度", "逐年", "变化", "变动", "好转", "恶化")):
                helpers.append(
                    ImplementationHelper(
                        module="core.skill_runtime.standard_financial_apis",
                        name="get_pledge_historical_series",
                        signature="symbol: str, start_date: str = None, end_date: str = None, years: int = None, period: str = 'year', source: str = None",
                        description="Returns the equity pledge trend within the specified time period, supporting year/quarter/month statistics, including the pledge ratio at the end of each cycle, the number of outstanding shares, the number of active pledges, and the trend direction of automatic evaluation (improving/worsening/stable)",
                        reason="The priority function for pledge trend analysis supports customized start and end dates and statistical granularity to directly determine the improvement/deterioration of risks.",
                        data_source_handling="self_contained",
                    )
                )
        return helpers

    @staticmethod
    def _convert_capability_hits_to_helpers(capability_hits: list) -> list:
        """Convert CapabilityIndexService.search_capabilities hits to ImplementationHelper.

        capability_hits Each item in is CapabilitySearchHit (including capability + score) . 
        Check ToolRegistry through registry_tool_id to obtain module_path and function_name.
        only keep bindable=True and source_type in (builtin_tool, mcp_tool) tools.
        """
        if not capability_hits:
            return []

        try:
            from core.tools.registry import get_tool_registry
            registry = get_tool_registry()
        except Exception as exc:
            logger.warning("⚠️ Vector search result conversion failed (ToolRegistry is not available): %s", exc)
            return []

        helpers = []
        seen_tool_ids = set()
        for hit in capability_hits:
            try:
                cap = hit.capability if hasattr(hit, "capability") else hit.get("capability", {})
                score = hit.score if hasattr(hit, "score") else hit.get("score", 0.0)
            except Exception:
                continue

            # Only bindable tool abilities are included (skip skill/external_skill, those are independent skills not functions)
            source_type = getattr(cap, "source_type", "") or (cap.get("source_type", "") if isinstance(cap, dict) else "")
            if source_type not in ("builtin_tool", "mcp_tool"):
                continue
            bindable = getattr(cap, "bindable", False) or (cap.get("bindable", False) if isinstance(cap, dict) else False)
            if not bindable:
                continue

            tool_id = getattr(cap, "registry_tool_id", None) or (cap.get("registry_tool_id") if isinstance(cap, dict) else None)
            if not tool_id or tool_id in seen_tool_ids:
                continue

            # Check ToolRegistry to get the function's module_path and function_name
            try:
                func = registry.get_function(tool_id)
            except Exception:
                func = None
            if func is None:
                continue

            module_path = getattr(func, "__module__", "") or ""
            function_name = getattr(func, "__name__", tool_id)
            # Only include modules under ALLOWED_CORE_PREFIXES (consistent with the static validator whitelist)
            from core.tools.external.static_validator import ALLOWED_CORE_PREFIXES
            allowed = any(module_path == p or module_path.startswith(p + ".") for p in ALLOWED_CORE_PREFIXES)
            if not allowed:
                continue

            name = getattr(cap, "name", "") or (cap.get("name", "") if isinstance(cap, dict) else "") or function_name
            description = getattr(cap, "description", "") or (cap.get("description", "") if isinstance(cap, dict) else "")
            when_to_use = getattr(cap, "when_to_use", "") or (cap.get("when_to_use", "") if isinstance(cap, dict) else "")

            # Read data_source_handling from ToolMetadata, passed to ImplementationHelper
            # Allow LLM to determine whether supplementary data sources are needed when designing skills in the skill workshop
            try:
                metadata = registry.get(tool_id)
                data_source_handling = getattr(metadata, "data_source_handling", "self_contained") if metadata else "self_contained"
            except Exception:
                data_source_handling = "self_contained"

            helpers.append(
                ImplementationHelper(
                    module=module_path,
                    name=function_name,
                    signature=f"{function_name}(symbol, **kwargs)",  # The signature is obtained by code_generator via describe_runtime_helper
                    description=description or when_to_use or name,
                    reason=f"vector search recall(score={score:.2f}) , Semantic matching skill requirements",
                    data_source_handling=data_source_handling,
                )
            )
            seen_tool_ids.add(tool_id)

        logger.info("🧭 vector search recall transformation: %d a hit → %d a ImplementationHelper", len(capability_hits), len(helpers))
        return helpers

    @staticmethod
    def _infer_blocked_paths(spec: SkillSpec) -> list[ImplementationIssue]:
        normalized = f"{spec.display_name} {spec.description} {spec.category}".lower()
        issues = [
            ImplementationIssue(
                path="direct provider import",
                reason="The generated Skill should not be imported directly into tradingagents.dataflows.provider/interface, but should be accessed through the skill_runtime public interface",
                severity="error",
            )
        ]
        if any(k in normalized for k in ("valuation", "估值", "peg", "pb", "pe", "dcf")):
            issues.append(
                ImplementationIssue(
                    path="default zero valuation outputs",
                    reason="Valuation Skills must not be output when key inputs are missing fair_value=0, peg_value=0 Wait for pseudo completion result",
                    severity="error",
                )
            )
        return issues

    @staticmethod
    def _infer_validation_checks(spec: SkillSpec) -> list[ValidationCheck]:
        if spec.validation_checks:
            return list(spec.validation_checks)

        checks: list[ValidationCheck] = [
            ValidationCheck(
                name="status_success",
                description="The output status must be success/ok and cannot end with error or false success.",
                check_type="status_success",
                rule_level="output",
                blocking=True,
                value_path="output",
                forbid_null=False,
            )
        ]
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

    @staticmethod
    def _infer_notes(spec: SkillSpec, recommendations: dict) -> list[str]:
        notes: list[str] = []
        if recommendations.get("external_sources"):
            notes.append("External data sources can be used to confirm the implementation path during the reconnaissance phase, but it does not mean that the final Skill can directly rely on its internal provider.")
        if spec.expected_output.fields:
            notes.append(f"期望输出字段: {', '.join(spec.expected_output.fields)}")
        return notes

    @staticmethod
    def _enrich_schema_bundle_guidance(
        report: ImplementationFactReport,
        schema_context: Dict[str, Any],
    ) -> None:
        report.schema_bundle_context = dict(schema_context)
        report.confidence = max(report.confidence, 0.72)

        method = schema_context.get("method") or {}
        contract = schema_context.get("contract") or {}
        verifier_rule = schema_context.get("verifier_rule") or {}
        applicability_rules = schema_context.get("applicability_rules") or {}

        method_id = str(schema_context.get("method_id") or method.get("id") or "")
        method_name = str(method.get("name") or method_id or "schema_method")
        method_objective = str(method.get("objective") or "").strip()
        if method_name:
            if method_objective:
                report.schema_facts.append(
                    ImplementationFact(
                        source=method_id or method_name,
                        fact=f"优先按 {method_name} 组织实现: {method_objective}",
                        evidence="financial_schema_bundle",
                    )
                )
            report.recommended_strategy = (
                f"{report.recommended_strategy}; press {method_name} Organize input verification, indicator calculation and output conclusion"
                if report.recommended_strategy
                else f"按 {method_name} 组织输入校验、指标计算和输出结论"
            )

        required_metrics = list(method.get("required_metrics") or [])
        if required_metrics:
            report.schema_facts.append(
                ImplementationFact(
                    source=method_id or method_name,
                    fact=f"方法要求优先获取指标: {', '.join(required_metrics)}",
                    evidence="financial_schema_bundle",
                )
            )

        required_fields = list(method.get("required_fields") or [])
        if required_fields:
            report.schema_facts.append(
                ImplementationFact(
                    source=method_id or method_name,
                    fact=f"方法要求检查输入字段: {', '.join(required_fields)}",
                    evidence="financial_schema_bundle",
                )
            )

        contract_id = str(schema_context.get("contract_id") or contract.get("id") or "")
        contract_required_fields = [
            str((field_def or {}).get("field_name") or "").strip()
            for field_def in contract.get("required_fields") or []
            if str((field_def or {}).get("field_name") or "").strip()
        ]
        if contract_required_fields:
            report.schema_facts.append(
                ImplementationFact(
                    source=contract_id or "output_contract",
                    fact=f"输出必须覆盖契约字段: {', '.join(contract_required_fields)}",
                    evidence="financial_schema_bundle",
                )
            )

        narrative_requirements = [str(item).strip() for item in contract.get("narrative_requirements") or [] if str(item).strip()]
        if narrative_requirements:
            report.notes.append(f"schema Output narrative requirements: {'; '.join(narrative_requirements[:4])}")

        prohibited_patterns = [str(item).strip() for item in contract.get("prohibited_patterns") or [] if str(item).strip()]
        if prohibited_patterns:
            for pattern in prohibited_patterns[:3]:
                report.blocked_paths.append(
                    ImplementationIssue(
                        path=f"schema_contract:{contract_id or 'output_contract'}",
                        reason=pattern,
                        severity="error",
                    )
                )

        verifier_id = str(schema_context.get("verifier_rule_id") or verifier_rule.get("id") or "")
        failure_message = str(verifier_rule.get("failure_message") or "").strip()
        if failure_message:
            report.notes.append(f"schema verifier failure semantics: {failure_message}")
        remediation_hint = str(verifier_rule.get("remediation_hint") or "").strip()
        if remediation_hint:
            report.notes.append(f"schema verifier Repair tips: {remediation_hint}")

        for rule_id, rule_object in applicability_rules.items():
            human_description = str(rule_object.get("human_description") or rule_id).strip()
            report.schema_facts.append(
                ImplementationFact(
                    source=rule_id,
                    fact=f"适用性规则: {human_description}",
                    evidence="financial_schema_bundle",
                )
            )
            rationale = str(rule_object.get("rationale") or "").strip()
            if rationale:
                report.notes.append(f"{rule_id}: {rationale}")

        existing_names = {item.name for item in report.validation_checks if item.name}
        for check in build_schema_generated_checks(schema_context):
            if check.name and check.name in existing_names:
                continue
            report.validation_checks.append(check)
            if check.name:
                existing_names.add(check.name)

        if verifier_id:
            report.notes.append(f"schema profile: {schema_context.get('profile')} / {verifier_id}")

    # ================================================================
    # Phase 1: Rule baseline (zero LLM cost)
    # ================================================================

    def _rule_based_analyze(self, spec: SkillSpec, capability_hits: list = None) -> ImplementationFactReport:
        """Pure rules-driven reconnaissance as a baseline and de-escalation scenario for LLM reconnaissance."""
        from core.skill_runtime.project_access import (
            inspect_field_coverage,
            inspect_stock_collection_schema,
            inspect_symbol_documents,
        )

        recommendations = self._analyzer.build_recommendations(spec=spec)

        # ── Requirement Type Diversion (Improvement Point 1): External API Integration vs. Local Data Reuse ──
        requirement_mode = self._classify_requirement_mode(spec)
        unknown_data_source = ""
        if requirement_mode == "external_api":
            data_source_raw = (getattr(spec, "data_source", "") or "").strip()
            if data_source_raw:
                from .external_data_source_catalog import is_known_external_source
                if not is_known_external_source(data_source_raw):
                    unknown_data_source = data_source_raw
            # External API integration mode: local stock collections and catalog external sources are irrelevant to requirements, clear them to avoid misdirection
            recommendations["stock_collections"] = []
            recommendations["external_sources"] = []

        report = ImplementationFactReport(
            task_summary=spec.description,
            recommended_strategy=(
                self._build_external_api_strategy(spec, unknown_data_source)
                if requirement_mode == "external_api"
                else self._build_strategy(spec, recommendations)
            ),
            confidence=0.45,
        )

        # ── Explicit annotation of data sources outside the directory (improvement point 2): no more silent fallback, registration of runtime gaps ──
        if unknown_data_source:
            from .external_data_source_catalog import EXTERNAL_DATA_SOURCE_CATALOG
            known_names = "、".join(item["display_name"] for item in EXTERNAL_DATA_SOURCE_CATALOG)
            gap_reason = (
                f"数据源 '{unknown_data_source}' 不在系统已知外部数据源目录（{known_names}）。"
                "This skill belongs to out-of-directory data source integration: the user needs to provide or confirm the interface specifications."
                " (URL, Request method, parameters, authentication method, return fields),"
                "Interface details and fields must not be fabricated when generating code; if specifications are incomplete, clarification should be made to the user first."
            )
            report.runtime_gaps.append(
                ImplementationIssue(
                    path=f"external_data_source:{unknown_data_source}",
                    reason=gap_reason,
                    severity="warning",
                )
            )
            report.notes.append(f"⚠️ {gap_reason}")
        symbol = self._extract_probe_symbol(spec)

        rule_based_helpers = self._infer_helpers(spec)
        logger.info(
            "\n" + "=" * 80 + "\n"
            "🔍 [Reconnaissance level Phase 1] Rule Baseline Analysis\n"
            f"   tool_id: {spec.tool_id}\n"
            f"   Requirement description: {spec.description[:80]}{'...' if len(spec.description) > 80 else ''}\n"
            f"   Rule recommendations helpers: {[h.module + '.' + h.name for h in rule_based_helpers]}\n"
            f"   Recommended local collection: {recommendations.get('stock_collections', [])}\n"
            f"   Recommended external data sources: {recommendations.get('external_sources', [])}\n"
            f"   Extracted test ticker: {symbol}\n"
            + "=" * 80
        )

        # Check if there are already enough helpers to avoid analyzing irrelevant collections
        has_direct_helpers = len(rule_based_helpers) > 0
        if has_direct_helpers:
            helper_names = [h.name for h in rule_based_helpers]
            # Classified according to helper's data_source_handling
            self_contained_helpers = [h for h in rule_based_helpers if h.data_source_handling == "self_contained"]
            local_only_helpers = [h for h in rule_based_helpers if h.data_source_handling == "local_only"]
            partial_helpers = [h for h in rule_based_helpers if h.data_source_handling == "partial"]

            logger.info(
                f"✅ [Reconnaissance level Phase 1] Found {len(rule_based_helpers)} directly available helper "
                f"({', '.join(helper_names)}), Data layer recommendations will be adjusted based on data source processing capabilities"
            )
            logger.info(
                f"   📊 Data source processing capabilities: self_contained={len(self_contained_helpers)}, "
                f"local_only={len(local_only_helpers)}, partial={len(partial_helpers)}"
            )

            # Intelligent decision-making data layer recommendation strategy:
            # - All self_contained: The helper is completely self-contained, and it is recommended to clear external data sources (LLM does not need to adjust the data source by itself)
            # - There is local_only: the helper only checks the local MongoDB and retains external data sources as a supplement (LLM may need to adjust the external API by itself)
            # - Yes partial: retain relevant data source recommendations
            all_self_contained = len(self_contained_helpers) == len(rule_based_helpers)
            has_local_only = len(local_only_helpers) > 0

            if all_self_contained:
                # All self-contained: clear external data sources and keep only stock_basic_info
                filtered_collections = []
                for col in recommendations.get("stock_collections") or []:
                    if col == "stock_basic_info":
                        filtered_collections.append(col)
                    else:
                        logger.info(f"   ⏭️  跳过集合分析: {col}（helper 已自包含数据获取）")
                recommendations["stock_collections"] = filtered_collections
                recommendations["external_sources"] = []

                report.notes.append(
                    f"✅ 已推荐 {len(rule_based_helpers)} 个 helper 函数（{', '.join(helper_names)}），"
                    "All for **self_contained** Type (encapsulated data source call, automatically call Tushare/AKShare or check local MongoDB)."
                    "LLM When generating code**Just call the helper directly. Do not implement the data source calling logic yourself.**"
                    " (Such as import tushare/akshare, directly call provider, etc.)."
                )

                # strategy clearly stated"call directly helper"
                helper_list_text = ", ".join(helper_names)
                report.recommended_strategy = (
                    f"Call the recommended helper function directly ({helper_list_text}) Get data and organize output."
                    "These helpers have encapsulated the data source calling logic, so there is no need to import tushare/akshare or check MongoDB yourself."
                )
            elif has_local_only:
                # There is local_only helper: keep external data sources as a supplement
                report.notes.append(
                    f"✅ 已推荐 {len(rule_based_helpers)} 个 helper 函数。"
                    f"where self_contained type {len(self_contained_helpers)} (the data source has been encapsulated and can be called directly),"
                    f"local_only Type {len(local_only_helpers)} (only check local MongoDB)."
                )
                report.notes.append(
                    "⚠️ local_only helper Only check the local MongoDB. If there is no data locally, LLM may need:\n"
                    "  1. Call self_contained helper to supplement data (such as get_external_historical_data)\n"
                    "  2. Or call external data sources (Tushare/AKShare) to supplement\n"
                    "  3. Handle no data locally in code (return no_data or downgrade to external API)"
                )
                # strategy Leave it as is (with local collections and external source recommendations as supplements)
            else:
                # partial or mixed case: keep data layer recommended
                report.notes.append(
                    f"✅ 已推荐 {len(rule_based_helpers)} 个 helper 函数，部分为 partial 类型。"
                    "LLM After calling the helper, other data sources or calculations may need to be supplemented."
                )

            if "估值" in spec.description or any(
                k in spec.description.lower() for k in ("valuation", "peg", "pb", "pe", "dcf")
            ):
                if "先确认价格" not in report.recommended_strategy:
                    report.recommended_strategy += "; First confirm the price, financial caliber and growth path, and then solidify the valuation formula"

        for collection in recommendations.get("stock_collections") or []:
            logger.info(f"📦 [Reconnaissance level Phase 1] Start analyzing a local collection: {collection}")
            report.schema_facts.append(
                ImplementationFact(
                    source=collection,
                    fact=f"推荐优先复用本地集合 {collection}",
                    evidence="RequirementAnalyzer.build_recommendations",
                )
            )
            self._enrich_collection_facts(
                report,
                collection,
                symbol,
                inspect_stock_collection_schema,
                inspect_field_coverage,
                inspect_symbol_documents,
            )

        for source in recommendations.get("external_sources") or []:
            logger.info(f"🌐 [Reconnaissance level Phase 1] Record external data source recommendations: {source}")
            report.schema_facts.append(
                ImplementationFact(
                    source=source,
                    fact=f"If local data is insufficient, documented data sources can be given priority. {source}",
                    evidence="RequirementAnalyzer.build_recommendations",
                )
            )

        report.available_helpers.extend(rule_based_helpers)

        #  [Key optimization] Directly verify the helper signature discovered in Phase 1, without the need for LLM to explore
        # In this way, Phase 2 can be skipped directly to avoid LLM exploring irrelevant tools.
        if rule_based_helpers:
            logger.info(
                f"🔍 [Reconnaissance level Phase 1] Start verification {len(rule_based_helpers)} signature of a helper..."
            )
            # NOTE: describe_runtime_helper is imported from recon_tools and returns a JSON string
            from .recon_tools import describe_runtime_helper, probe_interface

            # Fetch test stocks (for real helper calls)
            test_symbol = (
                getattr(spec, "test_input", {}).get("symbol")
                or getattr(spec, "test_input", {}).get("code")
                or ""
            )

            for helper in rule_based_helpers:
                try:
                    # helper.module is the complete path, such as "core.skill_runtime.standard_financial_apis"
                    # It is necessary to extract the module short name, such as "standard_financial_apis"
                    module_short = helper.module.split(".")[-1]
                    result_json = describe_runtime_helper(module_short, helper.name)
                    result = json.loads(result_json)
                    if "error" not in result:
                        helper.signature = result.get("signature", helper.signature)
                        # Fill in the description with the complete docstring, which will be used by the code generator
                        helper.description = result.get("docstring") or result.get("description") or ""
                        logger.info(
                            f"   ✅ {helper.name}: 签名验证成功"
                        )
                    else:
                        logger.warning(
                            f"   ⚠️  {helper.name}: 签名验证失败 - {result.get('error')}"
                        )
                except Exception as exc:
                    logger.warning(
                        f"   ⚠️  {helper.name}: 签名验证异常 - {exc}"
                    )

            #  [New] Added actual call to helper to verify availability + Financial experts judge the rationality of no_data
            # Avoid discovering after LLM generates code that the helper returns no_data (for example, the test stock itself has no pledge)
            if test_symbol:
                self._probe_helpers_and_judge(
                    rule_based_helpers, spec, test_symbol, report
                )

        # Recommended analysis tools for vector search recall (semantic matching, more accurate than keyword rules)
        if capability_hits:
            if requirement_mode == "external_api":
                # Improvement point 1: In external API integration mode, the local tool for vector recall has nothing to do with the specified external data source.
                # Do not include available_helpers (avoid"Data source has been covered"misleading conclusions)
                logger.info(
                    "🧭 [Reconnaissance level] External API integration mode: %d vector recall tools skipped (regardless of the specified external data source)",
                    len(capability_hits),
                )
                report.schema_facts.append(
                    ImplementationFact(
                        source="capability_index",
                        fact=(
                            f"向量搜索召回 {len(capability_hits)} 个本地工具，"
                            "The requirement is that the external API integration mode is not adopted (local tools have nothing to do with the specified external data source)"
                        ),
                        evidence="RequirementMode=external_api",
                    )
                )
            else:
                vector_helpers = self._convert_capability_hits_to_helpers(capability_hits)
                report.available_helpers.extend(vector_helpers)
                if vector_helpers:
                    report.schema_facts.append(
                        ImplementationFact(
                            source="capability_index",
                            fact=f"向量搜索召回 {len(vector_helpers)} 个语义相关工具（top score={capability_hits[0].score if capability_hits else 0:.2f}）",
                            evidence="CapabilityIndexService.search_capabilities",
                        )
                    )
        report.blocked_paths.extend(self._infer_blocked_paths(spec))
        report.validation_checks.extend(self._infer_validation_checks(spec))
        report.notes.extend(self._infer_notes(spec, recommendations))
        schema_context = resolve_financial_schema_context(spec)
        if schema_context:
            self._enrich_schema_bundle_guidance(report, schema_context)
        if report.sample_fields:
            report.confidence = max(report.confidence, 0.65)
        # ── Acceptance field consistency check (improvement point 3): lower the confidence level and prompt for clarification when the coverage is too low ──
        self._validate_expected_field_coverage(spec, report, requirement_mode)
        return report

    def _probe_helpers_and_judge(
        self,
        helpers: List[ImplementationHelper],
        spec,
        test_symbol: str,
        report: ImplementationFactReport,
    ) -> None:
        """Really call the helper to verify the availability, and call the financial expert to judge the rationality when no_data is returned.

        - If the helper returns success: write a sample return value structure to fact_report.notes,
          Help LLM know the field names (avoid guessing non-existent fields such as current_pledge_ratio)
        - If the helper returns no_data: Call financial experts to judge whether the business is reasonable.
          If it is unreasonable, recommend a more appropriate test stock write-in notes
        - If the helper is called abnormally: record the specific error and prompt LLM that the helper is not available
        """
        from .recon_tools import probe_interface
        from .financial_expert_advisor import get_financial_expert_advisor

        # Prepare financial expert advisor (lazy initialization, only called when no_data)
        advisor = None

        for helper in helpers[:3]:  # Verify up to first 3 helper
            try:
                # build sample_args
                sample_args = {"symbol": test_symbol}
                # Infer extra parameters based on helper name
                if "historical" in helper.name.lower() or "series" in helper.name.lower():
                    sample_args["years"] = 3

                probe_result_json = probe_interface(
                    f"{helper.module}.{helper.name}", sample_args
                )
                probe_result = json.loads(probe_result_json)

                if not probe_result.get("success"):
                    # The call itself failed
                    error_msg = probe_result.get("error", "未知错误")
                    report.notes.append(
                        f"⚠️ helper {helper.name} 真实调用失败: {error_msg}（建议 LLM 谨慎使用或换数据源）"
                    )
                    logger.warning(
                        f"⚠️ [侦察层] helper {helper.name} 真实调用失败: {error_msg}"
                    )
                    continue

                # Extract what the helper returns status
                preview = probe_result.get("preview", "")
                preview_dict = json.loads(preview) if isinstance(preview, str) else preview
                if not isinstance(preview_dict, dict):
                    preview_dict = {}

                helper_status = preview_dict.get("status", "unknown")
                helper_warnings = preview_dict.get("warnings", [])

                if helper_status == "success":
                    # ✅ helper Normal return data: write the return value structure sample notes + helper.description
                    # Even if the docstring is incomplete, the code generator can see the actual return fields (guaranteed mechanism)
                    field_keys = list(preview_dict.keys())
                    metrics_keys = (
                        list(preview_dict.get("metrics", {}).keys())
                        if isinstance(preview_dict.get("metrics"), dict)
                        else []
                    )
                    # Build return structure text (guaranteed)
                    return_struct = f"📋 实际返回字段: {field_keys}"
                    if metrics_keys:
                        return_struct += f", metrics subfield: {metrics_keys}"
                    # Append to helper.description (keep original docstring)
                    if helper.description:
                        helper.description = f"{helper.description}\n{return_struct}"
                    else:
                        helper.description = return_struct

                    report.notes.append(
                        f"✅ helper {helper.name} The real call is successful (status=success) . "
                        f"Return field: {field_keys}. "
                        f"metrics subfield: {metrics_keys}. "
                        f"LLM These field names should be read directly when generating code."
                    )
                    logger.info(
                        f"✅ [Reconnaissance level] helper {helper.name} The actual call is successful and the field is returned: {field_keys}"
                    )

                elif helper_status in ("no_data", "no_news", "no_pledge"):
                    # ⚠️ helper Return no_data: call financial experts to judge whether the business is reasonable
                    # Note: Do not extract the return field name here, because empty data will cause the code generator to misjudge the structure (cannot see
                    # Fields inside list elements such as holder_name/shares_wan/ratio_pct)
                    # The return structure should rely on the docstring of the Returns documentation or subsequent sandbox feedback
                    logger.info(
                        f"🔍 [侦察层] helper {helper.name} 返回 {helper_status}，调用财经专家判断合理性..."
                    )

                    if advisor is None:
                        advisor = get_financial_expert_advisor(
                            llm_client=self._get_client_safe(),
                            provider=self._provider,
                            model=self._model,
                        )

                    # Get basic stock information (industry, etc.)
                    stock_name = ""
                    industry = ""
                    try:
                        from core.skill_runtime.data_access import get_stock_basic_info

                        basic = get_stock_basic_info(test_symbol) or {}
                        stock_name = basic.get("name", "")
                        industry = basic.get("industry", "")
                    except Exception:
                        pass

                    # Infer data type description
                    data_type = self._infer_data_type(helper.name, spec)

                    judgment = advisor.judge_no_data_rationality(
                        stock_symbol=test_symbol,
                        stock_name=stock_name,
                        industry=industry,
                        skill_purpose=getattr(spec, "display_name", "")
                        or getattr(spec, "description", ""),
                        data_type=data_type,
                        helper_name=helper.name,
                        helper_warnings=helper_warnings,
                        skill_category=getattr(spec, "category", ""),
                    )

                    if judgment.is_rational:
                        # no_data The business is reasonable (e.g. bank shares are not pledged): tell LLM this is normal
                        report.notes.append(
                            f"ℹ️ helper {helper.name} 返回 {helper_status}（业务合理）。"
                            f"expert judgment: {judgment.reasoning}. "
                            f"Suggestions: Skill The code should return status=success and mark'There is no such data for this stock', "
                            f"Instead of returning error.{judgment.advice}"
                        )
                    else:
                        # no_data The business is unreasonable: share exchange recommended
                        report.notes.append(
                            f"⚠️ helper {helper.name} 返回 {helper_status}（业务不合理）。"
                            f"expert judgment: {judgment.reasoning}. "
                            f"It is recommended to exchange shares and try again."
                        )
                        if judgment.recommended_stocks:
                            for stock in judgment.recommended_stocks[:3]:
                                report.notes.append(
                                    f"  推荐测试股票: {stock.get('code')} {stock.get('name')} - {stock.get('reason')}"
                                )
                        if judgment.advice:
                            report.notes.append(f"  专家建议: {judgment.advice}")

                        # Write recommended stocks into schema_facts to facilitate subsequent pipeline reading
                        if judgment.recommended_stocks:
                            recommended_codes = ", ".join(
                                f"{s.get('code')}({s.get('name')})"
                                for s in judgment.recommended_stocks[:3]
                            )
                            report.schema_facts.append(
                                ImplementationFact(
                                    source="financial_expert_advisor",
                                    fact=f"建议换股测试: {recommended_codes}（原测试股票 {test_symbol} 无{data_type}）",
                                    evidence=f"helper {helper.name} 返回 {helper_status}，专家判断不合理",
                                )
                            )

                    logger.info(
                        f"🧠 [Reconnaissance level] Financial expert judgment: is_rational={judgment.is_rational}, "
                        f"confidence={judgment.confidence:.2f}"
                    )

                else:
                    # Other status (error, etc.)
                    report.notes.append(
                        f"⚠️ helper {helper.name} real call return status={helper_status}, "
                        f"warnings={helper_warnings}. LLM This situation should be handled."
                    )

            except Exception as exc:
                logger.warning(
                    f"⚠️ [侦察层] helper {helper.name} 真实调用异常: {exc}"
                )
                report.notes.append(
                    f"⚠️ helper {helper.name} 真实调用异常: {exc}（建议 LLM 谨慎使用）"
                )

    def _get_client_safe(self):
        """Obtain the LLM client safely and return if failed None"""
        try:
            return self._get_client()
        except Exception:
            return None

    @staticmethod
    def _infer_data_type(helper_name: str, spec) -> str:
        """Infer data type description based on helper name and spec"""
        name_lower = helper_name.lower()
        if "pledge" in name_lower:
            return "质押数据"
        if "financial" in name_lower or "annual" in name_lower:
            return "财务数据"
        if "news" in name_lower or "announcement" in name_lower:
            return "新闻/公告数据"
        if "valuation" in name_lower:
            return "估值数据"
        if "technical" in name_lower or "price" in name_lower:
            return "技术指标/价格数据"
        if "capital" in name_lower or "flow" in name_lower:
            return "资金流向数据"
        return "所需数据"

    @staticmethod
    def _enrich_collection_facts(
        report: ImplementationFactReport,
        collection: str,
        symbol: Optional[str],
        inspect_schema_fn=None,
        inspect_coverage_fn=None,
        inspect_symbol_fn=None,
    ) -> None:
        """Enrich collection facts with the project_access function."""
        if inspect_schema_fn is None:
            return
        try:
            schema_summary = inspect_schema_fn(collection, sample_size=12)
        except Exception as exc:
            report.runtime_gaps.append(
                ImplementationIssue(path=collection, reason=f"Unable to read collection schema summary: {exc}", severity="warning")
            )
            return

        sample_count = int(schema_summary.get("sample_count") or 0)
        top_fields = list(schema_summary.get("top_level_fields") or [])
        if sample_count <= 0:
            report.runtime_gaps.append(
                ImplementationIssue(path=collection, reason="There are currently no available samples in the collection, and field reconnaissance cannot be performed.", severity="warning")
            )
            return

        if top_fields:
            report.sample_fields[collection] = top_fields
            preview_fields = ", ".join(top_fields[:6])
            report.schema_facts.append(
                ImplementationFact(source=collection, fact=f"样本字段包括: {preview_fields}", evidence="inspect_stock_collection_schema")
            )
            if inspect_coverage_fn:
                try:
                    coverage_summary = inspect_coverage_fn(collection, top_fields[:min(6, len(top_fields))], sample_size=max(sample_count, 12))
                    coverage_parts = [f"{item.get('field')}={item.get('non_null_coverage', 0.0):.0%}" for item in coverage_summary.get("fields") or []]
                    if coverage_parts:
                        report.notes.append(f"{collection} 字段非空覆盖率: {', '.join(coverage_parts[:6])}")
                except Exception:
                    pass

        if not symbol or not inspect_symbol_fn:
            return
        try:
            symbol_docs = inspect_symbol_fn(collection, symbol, limit=2)
        except Exception as exc:
            report.runtime_gaps.append(
                ImplementationIssue(path=collection, reason=f"无法读取 symbol={symbol} 的样本: {exc}", severity="warning")
            )
            return
        symbol_documents = []
        if isinstance(symbol_docs, dict):
            symbol_documents = list(symbol_docs.get("documents") or [])
        elif isinstance(symbol_docs, list):
            symbol_documents = list(symbol_docs)

        if symbol_documents:
            first_doc = symbol_documents[0] if isinstance(symbol_documents[0], dict) else {}
            symbol_fields = list(first_doc.keys())
            matched_count = None
            if isinstance(symbol_docs, dict):
                matched_count = symbol_docs.get("matching_document_count")

            matched_text = f"，命中 {matched_count} 条" if matched_count is not None else ""
            report.notes.append(
                f"{collection} 中存在 {symbol} 的样本记录{matched_text}，首条摘要字段: {', '.join(symbol_fields)}"
            )
            existing = set(report.sample_fields.get(collection, []))
            new_fields = [f for f in symbol_fields if f not in existing]
            if new_fields and collection in report.sample_fields:
                report.sample_fields[collection].extend(new_fields)
        else:
            report.notes.append(f"{collection} 中未找到 {symbol} 的直接样本记录")

    # ================================================================
    # Phase 2: LLM drive reconnaissance
    # ================================================================

    def _llm_driven_analyze(
        self, client, spec: SkillSpec, rule_report: ImplementationFactReport,
        has_many_helpers: bool = False
    ) -> ImplementationFactReport:
        """Autonomous exploration through LLM function-calling produces enhanced fact reports.
        Args:
            has_many_helpers: True express helper >= 3, Only screening, limited to 2 rounds
        """
        from core.llm import Message

        start_time = time.time()
        tool_traces: List[ReconToolTrace] = []
        phase1_helper_names = {h.name for h in rule_report.available_helpers}

        # Register for Scouting Tools
        tool_defs = []
        for func in self._build_traced_tools(tool_traces):
            td = client.register_tool(func)
            tool_defs.append(td)

        # Build reconnaissance prompt: choose different system prompts according to the scenario
        system_prompt = self._build_recon_system_prompt(has_many_helpers=has_many_helpers)
        user_prompt = self._build_recon_user_prompt(spec, rule_report)
        max_rounds = 2 if has_many_helpers else MAX_RECON_TOOL_ROUNDS

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ]

        logger.info(
            f"\n{'─'*50}\n"
            f"🧭 [Reconnaissance level] LLM {'filter mode' if has_many_helpers else 'exploration mode'} | tool_id={spec.tool_id} | max_rounds={max_rounds}\n"
            f"{'─'*50}\n"
            f"📋 System Prompt ({len(system_prompt)} character):\n{system_prompt[:3000]}\n"
            f"{'...(Truncate)' if len(system_prompt) > 3000 else ''}\n"
            f"{'─'*50}\n"
            f"📝 User Prompt ({len(user_prompt)} character):\n{user_prompt[:2000]}\n"
            f"{'...(Truncate)' if len(user_prompt) > 2000 else ''}\n"
            f"🔧 Available tools: {[td['function']['name'] for td in tool_defs]}\n"
            f"{'─'*50}"
        )

        # Execute tool call loop
        try:
            response = client.chat(
                messages,
                tools=tool_defs,
                auto_execute_tools=True,
                max_tool_rounds=max_rounds,
            )
        except Exception:
            self._log_tool_trace_summary(spec.tool_id, tool_traces, failed=True)
            raise

        elapsed = time.time() - start_time
        raw_output = response.content or ""

        logger.info(
            f"\n{'─'*50}\n"
            f"📥 [Reconnaissance level] LLM output ({len(raw_output)} character, {elapsed:.1f}s)\n"
            f"{'─'*50}\n"
            f"{raw_output[:3000]}\n"
            f"{'...(Truncate)' if len(raw_output) > 3000 else ''}\n"
            f"{'─'*50}"
        )

        # Parsing the LLM output is ImplementationFactReport
        report = self._parse_llm_report(raw_output, spec, rule_report)
        report.tool_traces = tool_traces
        report.confidence = max(report.confidence, 0.75)
        report.notes.append(f"工具调用次数: {len(tool_traces)}")
        report.notes.append(f"侦察耗时: {elapsed:.1f}s（LLM 驱动）")
        self._log_tool_trace_summary(spec.tool_id, tool_traces, failed=False)

        # Phase 2 Summary log after analysis is completed
        if tool_traces:
            phase1_helper_names = {h.name for h in rule_report.available_helpers}
            phase2_helpers = set()
            phase2_collections = set()
            for trace in tool_traces:
                if trace.tool_name == "describe_runtime_helper":
                    func_name = trace.arguments.get("function_name", "")
                    if func_name:
                        phase2_helpers.add(func_name)
                elif trace.tool_name == "inspect_collection_schema":
                    col = trace.arguments.get("collection", "")
                    if col:
                        phase2_collections.add(col)

            redundant_collections = phase2_collections - phase1_helper_names
            if redundant_collections:
                helper_list = ", ".join(phase2_helpers)
                col_list = ", ".join(redundant_collections)
                logger.warning(
                    f"\n{'='*80}\n"
                    f"⚠️ [Reconnaissance level Phase 2] Possibly redundant collection probe detected\n"
                    f"   Phase 1 Found helpers: {', '.join(phase1_helper_names) or 'None'}\n"
                    f"   Phase 2 collection of probes: {col_list}\n"
                    f"   Suggestions: If the task can be completed through an existing helper, the system prompts can be simplified to avoid exploring irrelevant collections\n"
                    f"{'='*80}"
                )
        return report

    @staticmethod
    def _truncate_log_text(text: str, limit: int = 1600) -> str:
        raw = str(text or "")
        if len(raw) <= limit:
            return raw
        head = raw[:1000]
        tail = raw[-400:]
        return f"{head}\n...(中间省略 {len(raw) - 1400} 字符)...\n{tail}"

    @classmethod
    def _log_tool_trace_summary(
        cls,
        tool_id: str,
        tool_traces: List[ReconToolTrace],
        *,
        failed: bool,
    ) -> None:
        if not tool_traces:
            logger.info("🧭 [Reconnaissance level] No tool call trace | tool_id=%s | failed=%s", tool_id, failed)
            return

        logger.info(
            "🧭 [Reconnaissance level] Tool call trajectory summary | tool_id=%s | count=%s | failed=%s",
            tool_id,
            len(tool_traces),
            failed,
        )
        for index, trace in enumerate(tool_traces, start=1):
            logger.info(
                "🧭 [Reconnaissance level] Tool trajectory[%s] | tool=%s | success=%s | duration_ms=%s | result_chars=%s | args=%s\n%s",
                index,
                trace.tool_name,
                trace.success,
                trace.duration_ms,
                trace.result_chars,
                json.dumps(trace.arguments or {}, ensure_ascii=False, default=str),
                cls._truncate_log_text(trace.result_preview or trace.error or ""),
            )

    @staticmethod
    def _build_traced_tools(tool_traces: List[ReconToolTrace]) -> List[callable]:
        traced_tools: List[callable] = []

        for func in RECON_TOOLS:
            @wraps(func)
            def traced_func(*args, __func=func, **kwargs):
                started = time.time()
                arguments: Dict[str, Any] = {}
                try:
                    bound = inspect.signature(__func).bind_partial(*args, **kwargs)
                    arguments = dict(bound.arguments)
                except Exception:
                    arguments = {"args": list(args), **kwargs}

                try:
                    logger.info(
                        "🧭 [Reconnaissance level] Call tool | tool=%s | args=%s",
                        __func.__name__,
                        json.dumps(arguments, ensure_ascii=False, default=str),
                    )
                    result = __func(*args, **kwargs)
                    preview = str(result)
                    logger.info(
                        "🧭 [Reconnaissance level] tool returns | tool=%s | chars=%s\n%s",
                        __func.__name__,
                        len(preview),
                        DefaultReconnaissanceController._truncate_log_text(preview),
                    )
                    tool_traces.append(
                        ReconToolTrace(
                            tool_name=__func.__name__,
                            arguments=arguments,
                            success=True,
                            duration_ms=round((time.time() - started) * 1000, 2),
                            result_chars=len(preview),
                            result_preview=preview[:400],
                        )
                    )
                    return result
                except Exception as exc:
                    logger.warning(
                        "🧭 [Reconnaissance level] Tool exception | tool=%s | args=%s | error=%s",
                        __func.__name__,
                        json.dumps(arguments, ensure_ascii=False, default=str),
                        exc,
                    )
                    tool_traces.append(
                        ReconToolTrace(
                            tool_name=__func.__name__,
                            arguments=arguments,
                            success=False,
                            duration_ms=round((time.time() - started) * 1000, 2),
                            result_chars=0,
                            error=str(exc),
                        )
                    )
                    raise

            traced_tools.append(traced_func)

        return traced_tools

    # ================================================================
    # Prompt build & Output parsing
    # ================================================================

    @staticmethod
    def _build_recon_system_prompt(has_many_helpers: bool = False) -> str:
        if has_many_helpers:
            # helper More scenarios: only screening, no exploration
            return (
                "You are a Skill code generation pre-reconnaissance agent.\n"
                "##  [Important constraints] Current scene: Phase 1 found 3+ candidates helper\n"
                "Your task is very simple: you only need to filter out the most relevant 3-4 from the [Rule Baseline Recommendation Helper] list.\n"
                "You don t need to explore any new tools, new collections, or new functions! No need to call list_* Series of tools!\n\n"
                "## the only thing allowed\n"
                "1. Use describe_runtime_helper to verify the signature of a candidate helper (only if you need to confirm parameter details)\n"
                "2. Select the most relevant 3-4 from the candidate list and fill in available_helpers\n\n"
                "## Absolutely prohibited\n"
                "❌ Forbidden to call list_available_collections\n"
                "❌ Forbidden to call list_runtime_functions\n"
                "❌ Forbidden to call list_analysis_tools\n"
                "❌ Forbidden to call list_external_data_sources\n"
                "❌ Disable calling inspect_collection_schema to view collections that are not in the recommended list\n\n"
                "## Output format\n"
                "Only a pure JSON object is output, including task_summary, recommended_strategy, available_helpers (3-4 filtered ones), schema_facts, and confidence.\n"
                "Number of tool call rounds: 2 rounds at most, don t do unnecessary exploration!"
            )
        
        # helper Lesser scenarios: normal exploration (alternative branch, usually don't get this far)
        return (
            "You are a Skill code generation pre-reconnaissance agent.\n"
            "Your task is to collect minimal but sufficient implementation facts by calling tools to help the subsequent code generator write correct and runnable Python functions.\n\n"
            "## Core Principle: Explore on demand, avoid redundancy\n"
            "... (The original system prompt remains unchanged)..."
        )

    @staticmethod
    def _build_recon_user_prompt(spec: SkillSpec, rule_report: ImplementationFactReport) -> str:
        data_contract_doc = build_data_contract_doc_for_skill(spec)
        factor_catalog_doc = build_factor_catalog_prompt_context(
            spec.description,
            category=spec.category,
            expected_fields=list(spec.expected_output.fields or []),
        )
        parts = [
            f"## 待实现的 Skill\n"
            f"- tool_id: {spec.tool_id}\n"
            f"- Name: {spec.display_name}\n"
            f"- Description: {spec.description}\n"
            f"- Classification: {spec.category}\n",
        ]
        if spec.parameters:
            param_lines = [f"  - {p.name}: {p.type} (默认: {p.default})" for p in spec.parameters]
            parts.append(f"- 参数:\n" + "\n".join(param_lines))
        if spec.expected_output.fields:
            parts.append(f"- 期望输出字段: {', '.join(spec.expected_output.fields)}")
        if spec.test_input:
            parts.append(f"- 测试输入: {json.dumps(spec.test_input, ensure_ascii=False)}")

        # Additional rule baseline known facts
        if rule_report.schema_facts:
            baseline_facts = [f"  - [{f.source}] {f.fact}" for f in rule_report.schema_facts[:5]]
            parts.append(f"\n## Rule baseline known facts (from vector search + Static analysis, already trusted)\n" + "\n".join(baseline_facts))
        if rule_report.available_helpers:
            helper_lines = []
            for h in rule_report.available_helpers[:5]:
                ds = h.data_source_handling or "self_contained"
                helper_lines.append(f"  - {h.module}.{h.name} [数据源:{ds}]: {h.reason}")
            parts.append(
                "\n## Rule baseline recommendation Helper (from vector search, high confidence)\n"
                + "Data source tag: self_contained=self contained(call directly); local_only=local only MongoDB(May need to supplement external data sources); partial=partial coverage\n"
                + "\n".join(helper_lines)
                + "\n\n⚠️ These helpers have been filtered by semantic matching,**Just verify the signature with describe_runtime_helper**, "
                "Do not use list_runtime_functions to re-list. If the signature matches the requirements, add available_helpers output directly.\n"
                "⚠️ When selecting a helper, pay attention to the data source tag: if there is no local data for the local_only helper, you need to add an external data source call in the skill; just call the self_contained helper directly."
            )
        if data_contract_doc:
            parts.append(f"\n## 任务相关数据契约\n{data_contract_doc}")
        if factor_catalog_doc:
            parts.append(
                "\n## 任务相关因子白名单\n"
                f"{factor_catalog_doc}\n"
                "Please focus on verifying whether the helpers, field paths and reusable bundles corresponding to these factors are sufficient, and do not misjudge existing factors in the catalog as new gaps."
            )

        # Additional recommendation collection (extracted from schema_facts of rule_report)
        recommended_collections = [
            f.source for f in (rule_report.schema_facts or [])
            if "推荐优先复用本地集合" in (f.fact or "")
        ]
        if recommended_collections:
            parts.append(
                "\n## Rule baseline recommendation set (trusted, just verify the fields directly)\n"
                + "\n".join(f"  - {c}" for c in recommended_collections[:4])
                + "\n\n⚠️ These collections have been filtered through requirements analysis,**Just verify the fields with inspect_collection_schema**, "
                "Do not use list_available_collections to re-list all collections."
            )

        parts.append(
            "\n## Request\n"
            "Please first understand the field hierarchy according to the data contract, and then verify the critical path through tool calls. When outputting, keep only the minimum set of facts that will affect the code implementation, and do not write a long solution description.\n"
            "⚠️ Up to 6 rounds of tool calls. Each round must have a clear purpose. If the baseline has recommended helpers and collections, validation can ideally be completed in 2-3 rounds."
        )
        return "\n".join(parts)

    @staticmethod
    def _parse_llm_report(
        raw_output: str,
        spec: SkillSpec,
        rule_report: ImplementationFactReport,
    ) -> ImplementationFactReport:
        """Parse LLM output text, extract JSON and build ImplementationFactReport.

        Parsing strategy:
        1. try to start from ```json ... ``` code block.
        2. Try json.loads the entire text directly.
        3. If all else fails, use rule_report as a fallback and append the LLM text to notes.
        """
        parsed: Optional[Dict[str, Any]] = None

        # Strategy 1: Extract ```json ... ``` block
        import re
        json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)```", raw_output, re.DOTALL)
        for block in json_blocks:
            try:
                parsed = json.loads(block.strip())
                break
            except (json.JSONDecodeError, ValueError):
                continue

        # Strategy 2: Directly try to parse the entire paragraph
        if parsed is None:
            try:
                parsed = json.loads(raw_output.strip())
            except (json.JSONDecodeError, ValueError):
                pass

        # Strategy 3: Downgrade
        if not isinstance(parsed, dict):
            logger.warning("⚠️ Recon layer cannot parse JSON from LLM output, downgraded to rule reporting")
            rule_report.notes.append(f"LLM Recon output failed to parse to JSON and has been downgraded. First 500 words of raw output: {raw_output[:500]}")
            return rule_report

        # Build from parsed dict report
        report = ImplementationFactReport(
            task_summary=parsed.get("task_summary", spec.description),
            recommended_strategy=parsed.get("recommended_strategy", rule_report.recommended_strategy),
            confidence=float(parsed.get("confidence", 0.75)),
        )
        expected_fields = set(spec.expected_output.fields or [])

        # available_helpers
        for h in parsed.get("available_helpers") or []:
            if isinstance(h, dict) and h.get("name"):
                helper_name = h["name"]
                # Priority is given to using data_source_handling output by LLM; otherwise, check ToolRegistry to obtain
                data_source_handling = str(h.get("data_source_handling", "") or "").strip()
                if not data_source_handling:
                    try:
                        from core.tools.registry import get_tool_registry
                        registry = get_tool_registry()
                        metadata = registry.get(helper_name) or registry.get_tool(helper_name)
                        if metadata:
                            data_source_handling = getattr(metadata, "data_source_handling", "self_contained")
                    except Exception:
                        pass
                    if not data_source_handling:
                        data_source_handling = "self_contained"
                report.available_helpers.append(
                    ImplementationHelper(
                        module=h.get("module", ""),
                        name=helper_name,
                        signature=h.get("signature", ""),
                        reason=h.get("reason", ""),
                        data_source_handling=data_source_handling,
                    )
                )

        # schema_facts
        for f in parsed.get("schema_facts") or []:
            if isinstance(f, dict) and f.get("fact"):
                report.schema_facts.append(
                    ImplementationFact(
                        source=f.get("source", ""),
                        fact=f["fact"],
                        evidence=f.get("evidence", ""),
                    )
                )

        # sample_fields
        for coll, fields in (parsed.get("sample_fields") or {}).items():
            if isinstance(fields, list):
                report.sample_fields[coll] = [str(f) for f in fields]

        # blocked_paths
        for issue in parsed.get("blocked_paths") or []:
            if isinstance(issue, dict):
                report.blocked_paths.append(
                    ImplementationIssue(
                        path=issue.get("path", ""),
                        reason=issue.get("reason", ""),
                        severity=issue.get("severity", "error"),
                    )
                )

        # runtime_gaps
        for issue in parsed.get("runtime_gaps") or []:
            if isinstance(issue, dict):
                report.runtime_gaps.append(
                    ImplementationIssue(
                        path=issue.get("path", ""),
                        reason=issue.get("reason", ""),
                        severity=issue.get("severity", "warning"),
                    )
                )

        # validation_checks
        for vc in parsed.get("validation_checks") or []:
            if isinstance(vc, dict):
                raw_type = str(vc.get("check_type", "custom") or "custom").strip().lower()
                field_name = str(vc.get("field", "") or "").strip()

                if raw_type in ("business", "business_check", "custom"):
                    report.notes.append(
                        f"Ignore unenforceable business description rules: {vc.get('description') or vc.get('name') or raw_type}"
                    )
                    continue

                normalized_type = raw_type
                if raw_type in ("input_validation", "input", "input_check", "output", "output_check", "status"):
                    normalized_type = "status_success"
                elif raw_type in ("data_validation", "data", "data_check"):
                    normalized_type = "required_field" if field_name else "required_non_empty_payload"

                if normalized_type == "required_field" and field_name and expected_fields and field_name not in expected_fields:
                    report.notes.append(f"Ignore scouting field rules that are not included in the spec output: {field_name}")
                    continue

                report.validation_checks.append(
                    ValidationCheck(
                        name=vc.get("name", "") or (f"required_field:{field_name}" if normalized_type == "required_field" and field_name else normalized_type),
                        description=vc.get("description", ""),
                        required=vc.get("required", True),
                        check_type=normalized_type,
                        rule_level="output" if normalized_type == "status_success" else "data",
                        blocking=vc.get("blocking", True),
                        field=field_name,
                        value_path="output" if normalized_type == "status_success" else vc.get("value_path", "data"),
                        forbid_null=False if normalized_type == "status_success" else vc.get("forbid_null", False),
                    )
                )

        # notes
        for note in parsed.get("notes") or []:
            if isinstance(note, str):
                report.notes.append(note)

        # Add key information that is present in rule_report but missing from the LLM report
        if not report.blocked_paths and rule_report.blocked_paths:
            report.blocked_paths.extend(rule_report.blocked_paths)
        if not report.validation_checks and rule_report.validation_checks:
            report.validation_checks.extend(rule_report.validation_checks)

        # Added available_helpers: Helpers recommended by the Phase 1 rule baseline may be missed by LLM in Phase 2,
        # Must be retained to ensure key helpers (such as get_pledge_risk_profile) are visible to the code generation phase
        if rule_report.available_helpers:
            existing_helper_names = {h.name for h in report.available_helpers if h.name}
            for base_helper in rule_report.available_helpers:
                if base_helper.name and base_helper.name not in existing_helper_names:
                    report.available_helpers.append(base_helper)
                    existing_helper_names.add(base_helper.name)

        existing_names = {item.name for item in report.validation_checks if item.name}
        for base_check in spec.validation_checks:
            if base_check.name and base_check.name in existing_names:
                continue
            report.validation_checks.append(base_check)

        deduped_checks: list[ValidationCheck] = []
        seen_names: set[str] = set()
        for check in report.validation_checks:
            dedupe_name = check.name or f"{check.check_type}:{check.field}"
            if dedupe_name in seen_names:
                continue
            seen_names.add(dedupe_name)
            deduped_checks.append(check)
        report.validation_checks = deduped_checks

        return report