"""
requirements analyzer — Multiple rounds of conversational demand communication

Core competencies:
1. Clarity Assessment — Determine the clarity of user needs (HIGH/MEDIUM/LOW)
2. Boundary detection — Check whether requirements exceed the scope of a single Skill
3. Multiple rounds of dialogue — 1-3 Round of progressive requirements confirmation
4. Specification generation — Convert identified requirements into structured SkillSpec
"""

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.llm import UnifiedLLMClient, Message

from .external_data_source_catalog import (
    render_external_data_source_doc,
    select_relevant_external_data_sources,
)
from .stock_data_catalog import (
    render_stock_data_collection_doc,
    select_relevant_stock_collections,
)
from .financial_schema_context import (
    build_schema_constraint_hints,
    build_schema_generated_checks,
    get_contract_required_fields,
    resolve_financial_schema_context,
)
from core.skill_runtime import build_factor_catalog_prompt_context, infer_recommended_factor_packs
from .upgrade_patch import apply_upgrade_patch, build_upgrade_patch_prompt, parent_contract_to_json

# standard_financial_apis Summary of standard functions — Inject requirements analysis prompt words to let LLM know what capabilities have been built into the project
STANDARD_FINANCIAL_APIS_SUMMARY = (
    "## The project has built-in standard financial data capabilities (standard_financial_apis)\n"
    "The project provides 32 standard functions through core.skill_runtime.standard_financial_apis,"
    "Covers market conditions, finance, valuation, risks, peers, pledges and other scenarios. These functions**Automatically obtain data from project-configured data sources**"
    " (Tushare/akshare/local etc., the priority is configured uniformly by the database datasource_groupings collection),"
    "**Users do not need to, and should not, select data sources**. \n"
    "If the user s needs can be covered by the following functions, the user should be directly informed that the project has built-in this capability and do not guide the user to select a data source:\n"
    "- get_pledge_risk_profile: Equity pledge risk profile (pledge ratio, unreleased size, top pledging shareholders, risk level)\n"
    "- get_pledge_historical_series: Historical trend of equity pledge (supports customization of start and end dates, statistics of pledge ratio and number of unreleased shares by year/quarter/month, and automatic assessment of trend direction)\n"
    "- get_historical_financial_annual_series: Historical annual report financial sequence (revenue/net profit/ROE/gross profit margin/cash flow, etc.)\n"
    "- get_profitability_stability_metrics: Profitability stability indicator (mean/volatility/coefficient of variation)\n"
    "- get_cashflow_quality_trend: Cash flow quality trend (OCF/net profit, FCF/net profit, margin trend)\n"
    "- get_historical_valuation_percentile: Historical valuation quantile (PE/PB/PS/PCF quantile)\n"
    "- get_current_valuation_snapshot: Current valuation snapshot\n"
    "- get_debt_solvency_trend: Solvency Trends\n"
    "- get_margin_stability_metrics: Profit Stability Index\n"
    "- get_capital_efficiency_trend: Capital efficiency trends\n"
    "- get_growth_quality_metrics: growth quality index\n"
    "- get_single_stock_risk_profile: Individual stock risk portrait\n"
    "- get_shareholder_return_metrics: Shareholder return indicator (dividend/dividend rate)\n"
    "- get_risk_event_flags: Risk event flag\n"
    "- get_company_event_timeline: Timeline of company announcements and regulatory events\n"
    "- get_company_announcements: company announcement\n"
    "- get_business_segment_trend: Main business structure trends\n"
    "- get_peer_group: peer sample\n"
    "- get_peer_relative_growth / get_peer_relative_valuation / get_peer_relative_quality: peer relative analysis\n"
    "- get_industry_market_performance: Industry market performance\n"
    "- get_industry_fundamental_summary: Summary of industry fundamentals\n"
    "- get_capital_flow_series: Fund flow sequence\n"
    "- get_chip_distribution_context: Chip distribution context\n"
    "- get_security_master: Securities master data\n"
    "- get_adjusted_price_series: weighted price series\n"
    "- get_return_series: Return sequence\n"
    "- get_technical_indicator_series: Technical indicator historical series\n"
    "- get_volatility_metrics: volatility indicator\n"
    "- get_drawdown_metrics: retracement indicator\n"
    "- get_portfolio_risk_profile: Portfolio risk profile\n"
    "Only when user needs**Not covered by the above functions**Only then will we consider guiding users to use external data sources (such as AKShare/Tushare)."
    "However, priority should still be given to accessing it through the skill_runtime public interface instead of allowing users to directly select the data source."
)

from .skill_spec import (
    BoundaryCheck,
    ClarityLevel,
    ConversationRound,
    ImplementationFactReport,
    SessionStatus,
    SkillCreationSession,
    SkillHandoffContext,
    SkillParameter,
    SkillSpec,
    ValidationCheck,
)

logger = logging.getLogger(__name__)

ANALYZER_LLM_TIMEOUT_SECONDS = 180


SKILL_SEMANTICS_GUIDANCE = (
    "Skill Semantics: Skill is a functional implementation unit that is reusable, verifiable, and has clear boundaries."
    "It does not mean that it can only do data acquisition. Skill can do data acquisition, field sorting, format conversion, indicator calculation, rule judgment,"
    "Deterministic capabilities such as lightweight aggregation and templated description generation.\n"
    "Agent/Workflow Semantics: Responsible for demand understanding, task planning, multi-skill arrangement, open questioning, subjective comprehensive judgment,"
    "High-level decision-making and reasoning such as integration of research conclusions and generation of research observations.\n"
    "The core criterion for judging boundaries is not Is there any calculation or Is there an explanation , It s about whether the capability is certain, verifiable, and reusable."
    "And whether it still revolves around a single clear goal. If the explanation text is generated entirely based on fixed rules and input data, it can also be part of the Skill output."
)

SKILL_BOUNDARY_EXAMPLES = (
    "Examples that can be viewed as a single Skill:\n"
    "- Calculate the valuation channel based on the historical PB quantile, and output the current PB, quantile point, and corresponding price range\n"
    "- After obtaining the financial report, calculate the year-on-year/month-on-month growth rate and return structured results\n"
    "- Aggregate closely related data required for the same goal and output standardized summaries\n\n"
    "Examples that should be handed to Agent/Workflow:\n"
    "- Provide subjective investment conclusions based on macro, industry, financial reports, and news\n"
    "- Generate a complete research report after calling multiple independent Skills\n"
    "- Make an open strategy choice between multiple candidate methods and explain trade-offs\n"
)

# Explicit signal word for external HTTP API integration (appears in description/constraints)
EXTERNAL_API_SIGNAL_KEYWORDS = (
    "http://", "https://", "endpoint", "rest api", "open api",
    "公开接口", "公开http接口", "网页接口", "外部接口", "第三方接口", "爬取", "抓取",
)


def classify_requirement_mode(spec: Any) -> str:
    """Requirement type diversion: external_api (external API integration) / local_data (local data reuse, default).

    Determination signal (any hit is external_api):
    1. spec.data_source Explicitly specify the data source outside the directory (such as dongchedi / understand the car emperor);
    2. External interface integration signal words (URL, public interface, crawl, etc.) appear in the description or constraints.

    external_api Mode: Local stock collections are not recommended, and local tools for vector recall are not considered
    "Data source has been covered", The strategy is changed to integrate external interfaces directly, and the front end does not display local/catalog assets.
    """
    from .external_data_source_catalog import is_known_external_source

    data_source = (getattr(spec, "data_source", "") or "").strip()
    if data_source and not is_known_external_source(data_source):
        return "external_api"

    text = " ".join(
        [
            getattr(spec, "description", "") or "",
            " ".join(getattr(spec, "constraints", []) or []),
        ]
    ).lower()
    if any(k in text for k in EXTERNAL_API_SIGNAL_KEYWORDS):
        return "external_api"
    return "local_data"


class RequirementAnalyzer:
    """
    requirements analyzer

    Convert users natural language needs into structured SkillSpecs through multiple rounds of dialogue.
    """

    def __init__(
        self,
        llm_client: Optional[UnifiedLLMClient] = None,
        provider: str = "deepseek",
        model: Optional[str] = None,
        quick_llm_client: Optional[UnifiedLLMClient] = None,
    ):
        self._client = llm_client
        self._provider = provider
        self._model = model
        # Fast model client: light reasoning such as clarity assessment/boundary detection/dialogue reply/specification generation
        # Links are used first; if not configured, all will fall back to the main model, and the behavior will be consistent with the old version.
        self._quick_client = quick_llm_client

    def _get_client(self) -> UnifiedLLMClient:
        """懒加载 LLM 客户端"""
        if self._client is None:
            kwargs = {"timeout": ANALYZER_LLM_TIMEOUT_SECONDS}
            if self._model:
                kwargs["model"] = self._model
            self._client = UnifiedLLMClient.from_provider(self._provider, **kwargs)
        else:
            adapter = getattr(self._client, "_adapter", None)
            config = getattr(adapter, "config", None)
            if config and getattr(config, "timeout", 0) < ANALYZER_LLM_TIMEOUT_SECONDS:
                config.timeout = ANALYZER_LLM_TIMEOUT_SECONDS
                try:
                    adapter.initialize()
                except Exception as e:
                    logger.warning(f"Update requirements analysis LLM timeout failed: {e}")
        return self._client

    def _get_quick_client(self) -> Optional[UnifiedLLMClient]:
        """A dedicated fast model client for lightweight judgment; returns None when not configured (the caller falls back to the main model)."""
        if self._quick_client is None:
            return None
        adapter = getattr(self._quick_client, "_adapter", None)
        config = getattr(adapter, "config", None)
        if config and getattr(config, "timeout", 0) < ANALYZER_LLM_TIMEOUT_SECONDS:
            config.timeout = ANALYZER_LLM_TIMEOUT_SECONDS
            try:
                adapter.initialize()
            except Exception as e:
                logger.warning(f"Update fast model timeout failed: {e}")
        return self._quick_client

    def _chat_with_quick_fallback(
        self, messages: List[Message], *, stage: str
    ) -> str:
        """Light inference calls (dialog reply/spec generation): Prioritize fast models, fallback to main model on failure.

        Requirements dialogue (restatement/clarification/confirmation guidance) and specification generation (structured transcription) do not require depth
        Inference, fast non-thinking model reduces response from minutes to seconds; fast model not available
         (In case of arrears/timeout/empty reply), the main model will be rolled back to ensure the availability of functions.
        """
        quick = self._get_quick_client()
        if quick is not None:
            try:
                response = quick.chat(messages)
                content = (response.content or "").strip()
                if content:
                    return content
                logger.warning(f"{stage}: The quick model returns empty content and rolls back to the main model.")
            except Exception as exc:
                logger.warning(f"{stage}: The quick model call failed and the main model was rolled back.: {exc}")
        response = self._get_client().chat(messages)
        return (response.content or "").strip()

    @staticmethod
    def _raise_analysis_error(stage: str, error: Optional[Exception] = None) -> None:
        detail = str(error) if error else "LLM 未返回有效内容"
        raise RuntimeError(f"{stage}Failure:{detail}")

    # ==================== Robust JSON parsing ====================

    @staticmethod
    def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
        """Extracting JSON objects from LLM output, multi-policy fault tolerance.

        Strategy sequence:
        1. Extract ```json ... ``` Markdown code block
        2. Find the outermost level using brace depth matching { ... }
        3. Fix common LLM JSON errors and try again (trailing commas, single quotes, etc.)

        Returns:
            If the parsing is successful, dict will be returned. If all strategies fail, None will be returned.
        """
        if not raw or not raw.strip():
            return None

        text = raw.strip()

        # Strategy 1: Extract ```json ... ``` code block
        json_blocks = re.findall(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
        for block in json_blocks:
            result = RequirementAnalyzer._try_parse_json(block.strip())
            if result is not None:
                return result

        # Strategy 2: Braces depth matching (than greedy regular `\{.*\}` much more accurate)
        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        result = RequirementAnalyzer._try_parse_json(text[brace_start:i + 1])
                        if result is not None:
                            return result
                        break  # Matched to the outermost layer but failed to parse, enter the repair strategy

        # Strategy 3: Fix common LLM JSON errors and try again
        if brace_start >= 0:
            # Re-extract the outermost layer
            depth = 0
            end_idx = -1
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        end_idx = i
                        break
            if end_idx > brace_start:
                candidate = text[brace_start:end_idx + 1]
                candidate = RequirementAnalyzer._fix_common_json_errors(candidate)
                result = RequirementAnalyzer._try_parse_json(candidate)
                if result is not None:
                    return result

        return None

    @staticmethod
    def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
        """Attempts to parse JSON, returns None on failure."""
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
        return None

    @staticmethod
    def _fix_common_json_errors(text: str) -> str:
        """Fix common JSON format errors in LLM."""
        # Remove trailing commas: ,} and ,]
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        # Replace single quotes with double quotes (simple scenario)
        # Safe replacement only if value does not contain single quotes
        # text = text.replace("'", '"')  # Not safe, comment first
        # Fix true/false case problem
        text = re.sub(r"\bTrue\b", "true", text)
        text = re.sub(r"\bFalse\b", "false", text)
        text = re.sub(r"\bNone\b", "null", text)
        return text

    @staticmethod
    def _extract_tool_id_hint(text: str) -> str:
        match = re.search(r"(?:skill|Tools)[:: ]\s*([a-zA-Z][a-zA-Z0-9_]*)", text or "", re.IGNORECASE)
        if match:
            return match.group(1)
        if "pb" in (text or "").lower() or "市净率" in (text or ""):
            return "calculate_pb_valuation_band"
        return "new_skill"

    def _build_fallback_blueprint(self, text: str) -> Dict[str, Any]:
        normalized = (text or "").lower()
        recommendations = self.build_recommendations(conversation=text)
        tool_id = self._extract_tool_id_hint(text)
        category = recommendations.get("category_hint") or self._infer_category_hint(text)
        data_source_hint = recommendations.get("data_source_hint") or ""
        external_sources = recommendations.get("external_sources") or []
        primary_source = data_source_hint or (external_sources[0] if external_sources else "待确认")

        if "peg" in normalized:
            return {
                "tool_id": tool_id if tool_id != "new_skill" else "calculate_peg_valuation",
                "display_name": "PEG估值计算",
                "description": "Get based on stock code PE(TTM)and earnings growth rate, calculate PEG indicators and output structured valuation conclusions.",
                "category": "fundamentals",
                "data_source": primary_source,
                "parameters": [
                    {"name": "symbol", "type": "string", "description": "股票代码", "required": True},
                    {"name": "growth_years", "type": "integer", "description": "The growth caliber parameter currently only supports 1, which indicates the same caliber year-on-year, and does not represent the number of consecutive annual reports.", "required": False, "default": 1},
                ],
                "fields": [
                    "symbol", "name", "industry", "current_price", "pe_ttm",
                    "earnings_growth_rate", "peg_ratio", "valuation_level",
                    "assumptions", "failure_reason",
                ],
                "constraints": [
                    "Only structured, verifiable PEG results are output, no open-ended investment recommendations are generated.",
                    "The output field name must be stable, use earnings_growth_rate and peg_ratio, do not rewrite it as growth_rate or peg.",
                    "growth_years Currently, only 1 is supported, indicating year-on-year reporting for the same caliber; the quarterly end_date sequence of financial_indicators must not be mistaken for a continuous annual report sequence.",
                    "If the growth rate is missing, non-positive, or close to 0, the failure reason should be returned, and no forged default values ​​are allowed to continue the valuation.",
                ],
                "test_input": {
                    "symbol": "600519.SH",
                    "growth_years": 1,
                },
                "recommendations": recommendations,
            }

        if "pb" in normalized or "市净率" in text or "估值" in text:
            return {
                "tool_id": tool_id,
                "display_name": "PB估值区间计算",
                "description": "Based on historical PB quantiles and optional industry PB statistics, the stock valuation range and structural basis are output.",
                "category": "fundamentals",
                "data_source": primary_source,
                "parameters": [
                    {"name": "symbol", "type": "string", "description": "股票代码", "required": True},
                    {"name": "market", "type": "string", "description": "Market identification, e.g. CN/HK/US", "required": False, "default": "CN"},
                    {"name": "lookback_years", "type": "integer", "description": "历史回溯年数", "required": False, "default": 5},
                    {"name": "valuation_method", "type": "string", "description": "Valuation method: historical_percentile or historical_plus_industry", "required": False, "default": "historical_percentile"},
                    {"name": "include_industry_comparison", "type": "boolean", "description": "是否输出行业PB统计", "required": False, "default": True},
                ],
                "fields": [
                    "symbol", "current_pb", "pb_p20", "pb_p50", "pb_p80",
                    "valuation_lower", "valuation_mid", "valuation_upper",
                    "industry_pb_median", "industry_pb_mean", "peer_sample_size",
                    "assumptions", "invalidation_conditions", "data_as_of",
                ],
                "constraints": [
                    "Only structured, verifiable valuation results are output, and no open-ended investment recommendations are generated.",
                    "The valuation interval must be based on a fixed algorithm and no temporary subjective setting is allowed.",
                    "If there is an industry comparison, only the statistical results and sample size will be returned, and no long-form industry analysis will be carried out.",
                ],
                "test_input": {
                    "symbol": "600519.SH",
                    "market": "CN",
                    "lookback_years": 5,
                    "valuation_method": "historical_percentile",
                    "include_industry_comparison": True,
                },
                "recommendations": recommendations,
            }

        return {
            "tool_id": tool_id,
            "display_name": "新建功能 Skill",
            "description": "Provide reusable, verifiable structured capabilities around a single clear goal.",
            "category": category or "utility",
            "data_source": primary_source,
            "parameters": [
                {"name": "symbol", "type": "string", "description": "查询对象标识", "required": True},
            ],
            "fields": ["result", "data_as_of"],
            "constraints": [
                "Maintain a single clear goal and avoid expanding into open-ended analytical workflows.",
                "The output needs to be structured and verifiable.",
            ],
            "test_input": {"symbol": "600519.SH"},
            "recommendations": recommendations,
        }

    def _build_fallback_round1_response(self, user_message: str) -> str:
        blueprint = self._build_fallback_blueprint(user_message)
        recommendations = blueprint.get("recommendations") or {}
        stock_collections = recommendations.get("stock_collections") or []
        external_sources = recommendations.get("external_sources") or []
        return (
            "当前需求分析模型响应超时，我先按系统规则给你一个可继续执行的收敛草案，避免会话直接失败。\n\n"
            "## preliminary understanding\n"
            f"- candidate tool_id: {blueprint['tool_id']}\n"
            f"- Functional positioning: {blueprint['description']}\n"
            f"- Classification: {blueprint['category']}\n"
            f"- master data source: {blueprint['data_source']}\n"
            f"- Recommended local collections for reuse: {', '.join(stock_collections) if stock_collections else 'To be confirmed'}\n"
            f"- Recommend external sources: {', '.join(external_sources) if external_sources else 'To be confirmed'}\n\n"
            "## Let me help you tighten the boundaries of your responsibilities first\n"
            "- This Skill focuses on a single, deterministic valuation/calculation capability.\n"
            "- Can include necessary data acquisition, field sorting and fixed algorithm calculations.\n"
            "- We are not responsible for open-ended research reports, subjective investment conclusions and multi-stage arrangements.\n\n"
            "## Please confirm these 4 items first\n"
            "1. Is the valuation method fixed at historical_percentile, or is historical_plus_industry used?\n"
            f"2. Whether the main data source uses {blueprint['data_source']}? If not, please specify it directly.\n"
            "3. assumptions and invalidation_conditions accept being returned as a structured list of fields instead of a long explanation?\n"
            "4. Is the industry background limited to returning peer PB statistical results without conducting long-form industry analysis?"
        )

    def _build_fallback_round2_response(self, session: SkillCreationSession, user_message: str) -> str:
        history = self._collect_conversation(session, user_message)
        blueprint = self._build_fallback_blueprint(history)
        parameter_names = "、".join(item["name"] for item in blueprint["parameters"])
        output_fields = "、".join(blueprint["fields"])
        return (
            "需求分析模型再次超时，我先基于当前对话把技术规格收敛到可确认状态。\n\n"
            "## Current convergence results\n"
            f"- tool_id: {blueprint['tool_id']}\n"
            f"- description: {blueprint['description']}\n"
            f"- data_source: {blueprint['data_source']}\n"
            f"- Parameter suggestions: {parameter_names}\n"
            f"- Output field suggestions: {output_fields}\n\n"
            "## Waiting for your decision\n"
            "1. valuation_method Which fixed enumeration value should be used as the default value?\n"
            "2. Do you want to keep the include_industry_comparison parameter?\n"
            "3. Are industry_pb_median, industry_pb_mean, and peer_sample_size required in the output?\n"
            "4. If there is insufficient data, should partial results be returned with an error field, or should it fail directly?"
        )

    def _build_fallback_spec_confirmation(self, history: str) -> str:
        blueprint = self._build_fallback_blueprint(history)
        parameters = "、".join(f"{item['name']}({item['type']})" for item in blueprint["parameters"])
        fields = "、".join(blueprint["fields"])
        constraints = "；".join(blueprint["constraints"])
        recommendations = blueprint.get("recommendations") or {}
        return (
            "## Skill 规格确认\n"
            f"- **tool_id**: {blueprint['tool_id']}\n"
            f"- **Name**: {blueprint['display_name']}\n"
            f"- **Description**: {blueprint['description']}\n"
            f"- **Classification**: {blueprint['category']}\n"
            f"- **data source**: {blueprint['data_source']}\n"
            f"- **Recommended local collections for reuse**: {', '.join(recommendations.get('stock_collections') or []) or 'None'}\n"
            f"- **Recommend external sources**: {', '.join(recommendations.get('external_sources') or []) or 'None'}\n"
            f"- **parameters**: {parameters}\n"
            f"- **Return field**: {fields}\n"
            f"- **constraint**: {constraints}\n\n"
            "The above specifications are generated by the timeout degradation policy to ensure that the process can continue. Are the above specifications correct? Code generation will begin upon confirmation."
        )

    def _generate_fallback_spec(self, conversation: str) -> Optional[SkillSpec]:
        blueprint = self._build_fallback_blueprint(conversation)
        try:
            validation_checks = self._build_default_validation_checks(
                expected_fields=blueprint["fields"],
                category=blueprint["category"],
            )
            return SkillSpec(
                tool_id=blueprint["tool_id"],
                display_name=blueprint["display_name"],
                description=blueprint["description"],
                category=blueprint["category"],
                data_source=blueprint["data_source"] if blueprint["data_source"] != "待确认" else "",
                parameters=[
                    {
                        "name": item["name"],
                        "type": item["type"],
                        "description": item["description"],
                        "required": item.get("required", True),
                        "default": item.get("default"),
                    }
                    for item in blueprint["parameters"]
                ],
                expected_output={
                    "type": "dict",
                    "fields": blueprint["fields"],
                    "description": blueprint["description"],
                },
                validation_checks=validation_checks,
                constraints=blueprint["constraints"],
                test_input=blueprint["test_input"],
            )
        except Exception as e:
            logger.error(f"Heuristic SkillSpec generation failed: {e}")
            return None

    @staticmethod
    def _build_default_validation_checks(
        expected_fields: list[str],
        category: str = "",
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = [
            {
                "name": "status_success",
                "description": "The output status must be success/ok, and error or pseudo-success results cannot be returned.",
                "required": True,
                "check_type": "status_success",
                "rule_level": "output",
                "blocking": True,
                "value_path": "output",
                "forbid_null": False,
            }
        ]

        if expected_fields:
            for field_name in expected_fields:
                checks.append(
                    {
                        "name": f"required_field:{field_name}",
                        "description": f"成功输出时必须包含字段 {field_name}",
                        "required": True,
                        "check_type": "required_field",
                        "rule_level": "data",
                        "blocking": True,
                        "field": field_name,
                        "value_path": "data",
                        "forbid_null": True,
                    }
                )
        else:
            checks.append(
                {
                    "name": "required_non_empty_payload",
                    "description": "A non-empty data payload must be returned on successful output.",
                    "required": True,
                    "check_type": "required_non_empty_payload",
                    "rule_level": "data",
                    "blocking": True,
                    "value_path": "data",
                    "forbid_null": True,
                }
            )

        normalized = (category or "").lower()
        if normalized in ("fundamentals", "market", "technical", "utility", "news", "social"):
            checks.append(
                {
                    "name": "data_payload_object",
                    "description": "When output is successful, data should be a structured object or object list, and cannot just return an empty text description.",
                    "required": False,
                    "check_type": "required_non_empty_payload",
                    "rule_level": "data",
                    "blocking": False,
                    "value_path": "data",
                    "forbid_null": True,
                }
            )

        return checks

    @staticmethod
    def _normalize_validation_check_type(check_type: str, rule_level: str = "") -> str:
        normalized = (check_type or "").strip().lower()
        level = (rule_level or "").strip().lower()

        if normalized in ("status_success", "required_field", "required_non_empty_payload", "schema_condition"):
            return normalized
        if normalized in ("input", "input_check", "input_validation", "output", "output_check", "status"):
            return "status_success"
        if normalized in ("data", "data_check", "data_validation"):
            return "required_field"
        if normalized in ("business", "business_check", "custom"):
            return "custom"
        if level == "output":
            return "status_success"
        if level == "data":
            return "required_field"
        if level in ("business", "warning"):
            return "custom"
        return normalized or "custom"

    def _sanitize_validation_checks(
        self,
        checks: list[ValidationCheck],
        expected_fields: list[str],
    ) -> list[ValidationCheck]:
        sanitized: list[ValidationCheck] = []
        seen_names: set[str] = set()

        for check in checks:
            normalized_type = self._normalize_validation_check_type(check.check_type, check.rule_level)

            if normalized_type == "custom":
                continue

            if normalized_type == "status_success":
                normalized_check = ValidationCheck(
                    name=check.name or "status_success",
                    description=check.description or "The output status must be success/ok",
                    required=True,
                    check_type="status_success",
                    rule_level="output",
                    blocking=True,
                    value_path="output",
                    forbid_null=False,
                )
            elif normalized_type == "required_non_empty_payload":
                normalized_check = ValidationCheck(
                    name=check.name or "required_non_empty_payload",
                    description=check.description or "A non-empty data payload must be returned on successful output.",
                    required=check.required,
                    check_type="required_non_empty_payload",
                    rule_level="data",
                    blocking=check.blocking,
                    value_path=check.value_path or "data",
                    forbid_null=True,
                )
            elif normalized_type == "schema_condition":
                normalized_check = ValidationCheck(
                    name=check.name or "schema_condition",
                    description=check.description or "Must satisfy schema applicability rules",
                    required=check.required,
                    check_type="schema_condition",
                    rule_level=check.rule_level or "method",
                    blocking=check.blocking,
                    field=check.field,
                    value_path=check.value_path or "data",
                    forbid_null=check.forbid_null,
                    params=dict(check.params or {}),
                )
            else:
                field_name = (check.field or "").strip()
                if not field_name:
                    continue
                if expected_fields and field_name not in expected_fields:
                    continue
                normalized_check = ValidationCheck(
                    name=check.name or f"required_field:{field_name}",
                    description=check.description or f"成功输出时必须包含字段 {field_name}",
                    required=check.required,
                    check_type="required_field",
                    rule_level="data",
                    blocking=check.blocking,
                    field=field_name,
                    value_path=check.value_path or "data",
                    forbid_null=True,
                )

            dedupe_name = normalized_check.name or f"{normalized_check.check_type}:{normalized_check.field}"
            if dedupe_name in seen_names:
                continue
            seen_names.add(dedupe_name)
            sanitized.append(normalized_check)

        return sanitized

    @staticmethod
    def _enforce_known_skill_contracts(spec: SkillSpec) -> SkillSpec:
        tool_id = (spec.tool_id or "").strip().lower()
        description = (spec.description or "").lower()
        schema_context = resolve_financial_schema_context(spec)

        if tool_id == "calculate_peg_valuation" or "peg" in tool_id or "peg" in description:
            if (schema_context or {}).get("profile") == "peg":
                spec.category = "valuation"
                if not spec.expected_output.description:
                    spec.expected_output.description = "Return to PEG valuation results and key basis"
            else:
                spec.category = "fundamentals"
                canonical_fields = [
                    "symbol",
                    "name",
                    "industry",
                    "current_price",
                    "pe_ttm",
                    "earnings_growth_rate",
                    "peg_ratio",
                    "valuation_level",
                    "assumptions",
                    "failure_reason",
                ]
                alias_map = {
                    "growth_rate": "earnings_growth_rate",
                    "earnings_growth": "earnings_growth_rate",
                    "peg": "peg_ratio",
                    "failure_reasons": "failure_reason",
                    "invalidation_conditions": "failure_reason",
                }
                normalized_fields: list[str] = []
                seen_fields: set[str] = set()
                for field in list(spec.expected_output.fields or []) + canonical_fields:
                    normalized_field = alias_map.get(field, field)
                    if normalized_field in seen_fields:
                        continue
                    seen_fields.add(normalized_field)
                    normalized_fields.append(normalized_field)
                spec.expected_output.type = "dict"
                spec.expected_output.fields = normalized_fields
                if not spec.expected_output.description:
                    spec.expected_output.description = "Return to PEG valuation results and key basis"

            has_growth_years = any(param.name == "growth_years" for param in spec.parameters)
            if not has_growth_years:
                spec.parameters.append(
                    SkillParameter(
                        name="growth_years",
                        type="integer",
                        description="The growth caliber parameter currently only supports 1, which indicates the same caliber year-on-year, and does not represent the number of consecutive annual reports.",
                        required=False,
                        default=1,
                    )
                )
            if "growth_years" not in spec.test_input:
                spec.test_input["growth_years"] = 1

        return spec

    def _ensure_spec_validation_checks(self, spec: SkillSpec) -> SkillSpec:
        spec = self._enforce_known_skill_contracts(spec)
        spec = self._align_spec_with_schema_contract(spec)
        existing_checks = list(spec.validation_checks or [])
        if not existing_checks:
            spec.validation_checks = [
                ValidationCheck(**item)
                for item in self._build_default_validation_checks(
                    expected_fields=list(spec.expected_output.fields or []),
                    category=spec.category,
                )
            ]
            spec.validation_checks = self._sanitize_validation_checks(
                list(spec.validation_checks or []),
                list(spec.expected_output.fields or []),
            )
            return spec

        existing_checks = self._sanitize_validation_checks(
            existing_checks,
            list(spec.expected_output.fields or []),
        )

        normalized_names = {check.name for check in existing_checks if check.name}
        if "status_success" not in normalized_names:
            existing_checks.insert(
                0,
                ValidationCheck(**self._build_default_validation_checks([], spec.category)[0]),
            )

        has_data_check = any(
            check.check_type in ("required_field", "required_non_empty_payload")
            for check in existing_checks
        )
        if not has_data_check:
            fallback_checks = self._build_default_validation_checks(
                expected_fields=list(spec.expected_output.fields or []),
                category=spec.category,
            )[1:]
            existing_checks.extend(ValidationCheck(**item) for item in fallback_checks)

        spec.validation_checks = self._sanitize_validation_checks(
            existing_checks,
            list(spec.expected_output.fields or []),
        )
        return spec

    @staticmethod
    def _align_spec_with_schema_contract(spec: SkillSpec) -> SkillSpec:
        schema_context = resolve_financial_schema_context(spec)
        if not schema_context:
            return spec

        contract_required_fields = get_contract_required_fields(schema_context)
        if contract_required_fields:
            existing_fields = [str(field).strip() for field in list(spec.expected_output.fields or []) if str(field).strip()]
            merged_fields = []
            seen_fields = set()
            for field_name in contract_required_fields + existing_fields:
                if not field_name or field_name in seen_fields:
                    continue
                seen_fields.add(field_name)
                merged_fields.append(field_name)
            spec.expected_output.type = "dict"
            spec.expected_output.fields = merged_fields

        contract = schema_context.get("contract") or {}
        if not (spec.expected_output.description or "").strip():
            contract_name = str(contract.get("name") or schema_context.get("contract_id") or "").strip()
            method_name = str((schema_context.get("method") or {}).get("name") or "").strip()
            description_parts = [item for item in [contract_name, method_name] if item]
            if description_parts:
                spec.expected_output.description = "；".join(description_parts) + " 的结构化输出"

        schema_constraints = build_schema_constraint_hints(schema_context)
        if schema_constraints:
            existing_constraints = [str(item).strip() for item in list(spec.constraints or []) if str(item).strip()]
            merged_constraints = []
            seen_constraints = set()
            for item in existing_constraints + schema_constraints:
                if not item or item in seen_constraints:
                    continue
                seen_constraints.add(item)
                merged_constraints.append(item)
            spec.constraints = merged_constraints

        schema_checks = build_schema_generated_checks(schema_context)
        if schema_checks:
            existing_checks = list(spec.validation_checks or [])
            existing_names = {check.name for check in existing_checks if check.name}
            for check in schema_checks:
                if check.name and check.name in existing_names:
                    continue
                existing_checks.append(check)
                if check.name:
                    existing_names.add(check.name)
            spec.validation_checks = existing_checks

        return spec

    @staticmethod
    def _infer_category_hint(text: str) -> str:
        normalized = (text or "").lower()
        keyword_map = {
            "news": ["新闻", "快讯", "公告", "headline", "news", "舆情", "事件"],
            "fundamentals": ["财务", "报表", "营收", "净利润", "分红", "估值", "基本面", "roe"],
            "technical": ["技术指标", "均线", "macd", "rsi", "k线", "日线", "走势", "波动率"],
            "market": ["行情", "盘口", "资金流", "成交额", "实时", "quote", "snapshot"],
            "social": ["情绪", "社交", "讨论", "论坛"],
        }
        for category, keywords in keyword_map.items():
            if any(keyword in normalized for keyword in keywords):
                return category
        return "utility"

    @staticmethod
    def _infer_data_source_hint(text: str) -> str:
        normalized = (text or "").lower()
        for source in ("tushare", "akshare", "finnhub", "google news", "google", "eastmoney", "东方财富"):
            if source.lower() in normalized:
                return source
        return ""

    def _build_catalog_context(self, text: str) -> str:
        category = self._infer_category_hint(text)
        data_source = self._infer_data_source_hint(text)
        local_collections = select_relevant_stock_collections(
            category=category,
            description=text,
            data_source=data_source,
            max_items=3,
        )
        external_sources = select_relevant_external_data_sources(
            category=category,
            description=text,
            data_source=data_source,
            max_items=3,
        )
        local_doc = render_stock_data_collection_doc(
            collections=local_collections,
            focus_summary="、".join(item["collection"] for item in local_collections),
        )
        external_doc = render_external_data_source_doc(
            sources=external_sources,
            focus_summary="、".join(item["display_name"] for item in external_sources),
        )
        factor_doc = build_factor_catalog_prompt_context(
            text,
            category=category,
        )
        sections = [local_doc, external_doc]
        if factor_doc:
            sections.append(factor_doc)
        return "\n\n".join(section for section in sections if section.strip())

    def build_recommendations(
        self,
        *,
        spec: Optional[SkillSpec] = None,
        conversation: str = "",
        fact_report: Optional["ImplementationFactReport"] = None,
    ) -> Dict[str, Any]:
        if spec is not None:
            category = getattr(spec, "category", "") or self._infer_category_hint(getattr(spec, "description", ""))
            data_source = getattr(spec, "data_source", "") or self._infer_data_source_hint(getattr(spec, "description", ""))
            description = getattr(spec, "description", "")
            constraints = getattr(spec, "constraints", []) or []
            expected_output = getattr(spec, "expected_output", None)
            expected_fields = getattr(expected_output, "fields", []) if expected_output else []
            parameter_names = [getattr(param, "name", "") for param in getattr(spec, "parameters", []) or []]
        else:
            category = self._infer_category_hint(conversation)
            data_source = self._infer_data_source_hint(conversation)
            description = conversation
            constraints = []
            expected_fields = []
            parameter_names = []

        # Local collections and external sources are no longer recommended when the recommendation helper has been found by the recon layer——
        # helper Data access has been encapsulated inside the function, and directly recommending collections/sources will make users confused about which one should be used.
        # category_hint / data_source_hint / recommended_factor_packs Metadata is still returned.
        has_recon_helpers = bool(fact_report and getattr(fact_report, "available_helpers", None))

        # ── Detection of data sources outside the directory (improvement point 2): When the source explicitly specified by the user is not in a known directory,
        # Explicitly return unknown_data_source without fallback to recommend external sources to avoid misleading ──
        from .external_data_source_catalog import is_known_external_source
        unknown_data_source = ""
        if spec is not None:
            spec_source = (getattr(spec, "data_source", "") or "").strip()
            if spec_source and not is_known_external_source(spec_source):
                unknown_data_source = spec_source

        if unknown_data_source:
            stock_collections: List[str] = []
            external_sources: List[str] = []
        elif has_recon_helpers:
            stock_collections: List[str] = []
            external_sources: List[str] = []
        else:
            local_collections = select_relevant_stock_collections(
                category=category,
                description=description,
                data_source=data_source,
                constraints=constraints,
                expected_fields=expected_fields,
                parameter_names=parameter_names,
                max_items=3,
            )
            external_sources_list = select_relevant_external_data_sources(
                category=category,
                description=description,
                data_source=data_source,
                constraints=constraints,
                expected_fields=expected_fields,
                parameter_names=parameter_names,
                max_items=3,
            )
            stock_collections = [item["collection"] for item in local_collections]
            external_sources = [item["source_id"] for item in external_sources_list]

        return {
            "category_hint": category,
            "data_source_hint": data_source,
            "stock_collections": stock_collections,
            "external_sources": external_sources,
            "unknown_data_source": unknown_data_source,
            "requirement_mode": classify_requirement_mode(spec) if spec is not None else "local_data",
            "recommended_factor_packs": infer_recommended_factor_packs(
                description,
                category=category,
                expected_fields=list(expected_fields or []),
            ),
        }

    # ==================== Session management ====================

    def create_session(
        self,
        user_id: str = "",
        handoff_context: Optional[SkillHandoffContext] = None,
        iterate_skill_id: Optional[str] = None,
    ) -> SkillCreationSession:
        """Create a new SkillCreate session"""
        return SkillCreationSession(
            session_id=str(uuid.uuid4()),
            user_id=user_id,
            status=SessionStatus.GATHERING,
            handoff_context=handoff_context,
            iterate_skill_id=iterate_skill_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

    @staticmethod
    def _build_handoff_context_text(session: SkillCreationSession) -> str:
        context = session.handoff_context
        if not context:
            return ""

        lines = [
            "The current session comes from the handover of the upstream process and is not a new requirement out of thin air.",
            f"- 来源: {context.source or 'unknown'}",
        ]
        if context.source_name:
            lines.append(f"- 上游对象: {context.source_name}")
        if context.source_spec_id:
            lines.append(f"- 上游规格 ID: {context.source_spec_id}")
        if context.target_capability:
            lines.append(f"- 待补目标能力: {context.target_capability}")
        if context.handoff_intent:
            lines.append(f"- 上游交接意图: {context.handoff_intent}")
        if context.agent_goal:
            lines.append(f"- Upstream Agent target: {context.agent_goal}")
        if context.gap_context:
            lines.append(f"- 当前缺口上下文: {context.gap_context[:800]}")
        if context.searched_capabilities:
            lines.append("- Upstream retrieved/evaluated capabilities:")
            for item in context.searched_capabilities[:8]:
                lines.append(f"  - {str(item)[:500]}")
        if context.confirmed_data_sources:
            lines.append("- Upstream confirmed data source/helper:")
            for item in context.confirmed_data_sources[:8]:
                lines.append(f"  - {str(item)[:500]}")
        if context.user_clarifications:
            lines.append("- Key conclusions clarified by users:")
            for item in context.user_clarifications[:8]:
                lines.append(f"  - {str(item)[:500]}")
        if context.related_gaps:
            lines.append("- Related capability gaps in the same task:")
            for item in context.related_gaps[:8]:
                lines.append(f"  - {str(item)[:500]}")
        if context.known_failure_summaries:
            lines.append("- Summary of known failures in the same completion task (to avoid repeated pitfalls):")
            for item in context.known_failure_summaries[:5]:
                lines.append(f"  - {str(item)[:500]}")
        if context.known_verified_facts:
            lines.append("- Environmental facts have been verified in the same completion task:")
            for item in context.known_verified_facts[:8]:
                lines.append(f"  - {str(item)[:500]}")
        lines.extend([
            "- You need to first determine whether existing tools or skills can be reused.",
            "- Only when there is a real lack of implementation can the requirements be converged into a new minimum capability unit.",
        ])
        return "\n".join(lines)

    @staticmethod
    def _build_handoff_guardrails(session: SkillCreationSession) -> str:
        context = session.handoff_context
        if not context:
            return ""

        target_capability = context.target_capability or "上游指定能力"
        source_name = context.source_name or context.source or "Upstream Agent creation process"
        return (
            "## Upstream handover constraints (must be adhered to)\n"
            f"- This demand comes from {source_name} The handover of ability gaps is not an ordinary free brainstorming from scratch.\n"
            f"- You have to target capabilities around the upstream specified {target_capability} Continue to converge unless the user explicitly changes the question.\n"
            "- Do not secretly rewrite the target capabilities that have been confirmed by upstream into another implementation that you are more familiar with, such as Valuation analysis shrink into PB Valuation interval calculation . \n"
            "- If failure summaries or verified facts have been recorded for the same completion task, these known error paths must be explicitly avoided, and falsified data source/field assumptions must not be re-adopted.\n"
            "- If you judge that the complete goal is more like Agent/Workflow than a single Skill, clearly point out that this is an Agent-level goal, and position the current Skill as only one of the deterministic sub-abilities; do not pretend that the entire goal has been completely covered by a Skill.\n"
            "- If there is an existing skill that can be reused, the reuse plan should be pointed out first; if it does not exist, the minimum responsibility boundary of the new skill should be defined.\n"
        )

    def process_user_input(
        self,
        session: SkillCreationSession,
        user_message: str,
        skill_context: Optional[str] = None,
    ) -> Tuple[SkillCreationSession, str]:
        """
        Process user input and advance conversations

        Args:
            session: current session
            user_message: User messages
            skill_context: There is already a context for the Skill in iterative mode (JSON string)

        Returns:
            (Updated session, AI Reply to message)
        """
        session.updated_at = datetime.utcnow()

        # Determine whether it is iterative mode
        is_iteration = bool(session.iterate_skill_id)

        # If it is the first round, do clarity assessment and boundary detection first
        if session.current_round == 0:
            try:
                clarity = self._assess_clarity(user_message)
            except Exception as exc:
                logger.error("Clarity evaluation failed, downgraded to MEDIUM: %s", exc)
                clarity = ClarityLevel.MEDIUM
            session.clarity_level = clarity

            try:
                boundary_context = self._build_handoff_context_text(session)
                boundary = self._check_boundary(
                    user_message,
                    conversation_context=boundary_context or None,
                )
            except Exception as exc:
                logger.error("Boundary detection failed, downgraded to pass: %s", exc)
                boundary = BoundaryCheck(within_boundary=True, reason="Boundary detection fails and passes by default")
            session.boundary_check = boundary

            # If out of bounds, return splitting suggestions
            if not boundary.within_boundary:
                ai_msg = self._build_boundary_warning(boundary)
                round_obj = ConversationRound(
                    round_number=1,
                    ai_message=ai_msg,
                    user_message=user_message,
                )
                session.rounds.append(round_obj)
                session.current_round = 1
                return session, ai_msg

        # Advancing dialogue
        session.current_round += 1
        max_rounds = self._get_max_rounds(session.clarity_level)

        # Round 2 and beyond: Re-evaluate boundaries based on latest user feedback, complexity alerts will be updated accordingly
        if session.current_round >= 2:
            try:
                conversation = self._collect_conversation(session, user_message)
                boundary = self._check_boundary(user_message, conversation_context=conversation)
                session.boundary_check = boundary
            except Exception as exc:
                logger.error("The %dth round of boundary detection failed and was skipped.: %s", session.current_round, exc)

        if session.current_round >= max_rounds:
            # Iterative mode: The first round must not jump directly to the last round, at least one iteration guidance is required
            if is_iteration and session.current_round == 1:
                if skill_context:
                    try:
                        ai_msg = self._build_iteration_round1_response(
                            session, user_message, skill_context
                        )
                    except Exception as exc:
                        logger.error("The first round of requirements analysis in iterative mode failed to call LLM and used a downgrade reply.: %s", exc)
                        ai_msg = self._build_fallback_round1_response(user_message)
                else:
                    ai_msg = self._build_round1_response(session, user_message)
            else:
                # Final round: Generate specification confirmation
                try:
                    ai_msg = self._build_spec_confirmation(session, user_message)
                except Exception as exc:
                    logger.error("Last round of specification confirmation LLM call failed, using downgrade reply: %s", exc)
                    ai_msg = self._build_fallback_spec_confirmation(
                        self._collect_conversation(session, user_message)
                    )
        elif session.current_round == 1:
            # Round 1
            if is_iteration and skill_context:
                # Iteration mode: Use iteration-specific prompt words
                try:
                    ai_msg = self._build_iteration_round1_response(
                        session, user_message, skill_context
                    )
                except Exception as exc:
                    logger.error("The first round of requirements analysis in iterative mode failed to call LLM and used a downgrade reply.: %s", exc)
                    ai_msg = self._build_fallback_round1_response(user_message)
            else:
                # Normal mode: preliminary understanding + Disassembly of function points
                try:
                    ai_msg = self._build_round1_response(session, user_message)
                except Exception as exc:
                    logger.error("The first round of requirements analysis LLM call failed, use downgrade reply: %s", exc)
                    ai_msg = self._build_fallback_round1_response(user_message)
        else:
            # Round 2: Technology Refinement
            try:
                ai_msg = self._build_round2_response(session, user_message)
            except Exception as exc:
                logger.error("The second round of requirements analysis LLM call failed, use downgrade reply: %s", exc)
                ai_msg = self._build_fallback_round2_response(session, user_message)

        round_obj = ConversationRound(
            round_number=session.current_round,
            ai_message=ai_msg,
            user_message=user_message,
        )
        session.rounds.append(round_obj)

        return session, ai_msg

    def confirm_spec(
        self,
        session: SkillCreationSession,
        user_message: str,
        fact_report: Optional[ImplementationFactReport] = None,
        parent_contract: Optional[Dict[str, Any]] = None,
    ) -> Tuple[SkillCreationSession, Optional[SkillSpec]]:
        """
        After the user confirms the specifications, generate SkillSpec

        Args:
            session: current session
            user_message: User s confirmation message ("Confirm" / Additional modifications)
            fact_report: Recon report (recon pre-mode) for enhanced spec generation
            parent_contract: The parent version contract of the iteration mode (including complete parameters/constraints/code),
                When incoming, enter the upgrade patch mode: LLM only outputs delta, and the parent contract is inherited as it is.

        Returns:
            (Updated session, Generated SkillSpec or None)
        """
        # Collect all conversations
        conversation = self._collect_conversation(session, user_message)

        # LLM Generate structured SkillSpec
        spec = self._generate_spec(
            conversation, fact_report=fact_report, session=session,
            parent_contract=parent_contract,
        )

        if spec:
            session.spec = spec
            session.spec_confirmed = True
            session.status = SessionStatus.CONFIRMED
            session.updated_at = datetime.utcnow()

        return session, spec

    def preview_spec(
        self,
        session: SkillCreationSession,
        user_message: str = "确认",
        fact_report: Optional[ImplementationFactReport] = None,
        parent_contract: Optional[Dict[str, Any]] = None,
    ) -> Optional[SkillSpec]:
        """
        Only a SkillSpec preview is generated, the session state is not modified.
        Used to display the specification confirmation steps. After the user confirms, the confirm_spec execution pipeline is called.

        parent_contract: The parent version contract of iteration mode, when passed in, upgrade patch mode will be used.
        """
        conversation = self._collect_conversation(session, user_message)
        return self._generate_spec(
            conversation, fact_report=fact_report, session=session,
            parent_contract=parent_contract,
        )

    # ==================== Clarity Assessment ====================

    def _assess_clarity(self, user_message: str) -> ClarityLevel:
        """评估需求清晰度"""
        client = self._get_quick_client() or self._get_client()
        prompt = (
            "Please rate the clarity of the following user needs (1-5 points).\n"
            "5 points=Very clear (clear data sources, parameters, output),"
            "3 points=Average (has a theme but lacks details),"
            "1 points=Blurred (only general direction).\n\n"
            f"User needs: {user_message}\n\n"
            "Reply only with a number (1-5) and nothing else."
        )
        try:
            response = client.chat([Message(role="user", content=prompt)])
            score_text = (response.content or "3").strip()
            score = int(re.search(r"[1-5]", score_text).group())
        except Exception:
            score = 3

        if score >= 4:
            return ClarityLevel.HIGH
        elif score >= 3:
            return ClarityLevel.MEDIUM
        else:
            return ClarityLevel.LOW

    # ==================== Boundary detection ====================

    def _check_boundary(
        self, user_message: str, conversation_context: Optional[str] = None
    ) -> BoundaryCheck:
        """Detect whether requirements exceed the scope of a single Skill. If there is a history of dialogue, re-evaluate based on the latest consensus."""
        client = self._get_quick_client() or self._get_client()
        if conversation_context:
            prompt = (
                "You are a Skill boundary detection expert. A Skill should focus on a clear and reusable functional unit."
                "It can include necessary data acquisition, cleaning and transformation, formatting, deterministic calculation, rule judgment or lightweight aggregation;"
                "But it should not carry open-ended research, subjective investment conclusions, or orchestration of long links across multiple independent goals.\n\n"
                f"{SKILL_SEMANTICS_GUIDANCE}\n\n"
                f"{SKILL_BOUNDARY_EXAMPLES}\n"
                "**important**: After multiple rounds of dialogue, the user s needs may have been significantly adjusted, for example:\n"
                "- A certain sub-plan is selected (such as Plan A/B/C )\n"
                "- Get via API instead (instead of PDF parsing)\n"
                "- Reduced scope or simplified implementation\n\n"
                "you must base on**The latest round of clear choices for users**Re-evaluate rather than stick to your first-round judgment."
                "If the user has converged the requirements into a single clear capability, even if there is an internal need to combine closely related data sources or do deterministic calculations, it should not be mechanically judged as out of bounds."
                "Splitting is only recommended when the requirements simultaneously contain multiple independent functional goals, open analysis conclusions, or multi-stage workflows."
                "Don t show up Calculate  Valuation range  explanatory hypothesis  Industry background These words are automatically judged as Agent responsibilities and must be judged based on whether they are certain and verifiable.\n\n"
                f"Conversation history:\n{conversation_context}\n\n"
                "If it is determined to be out of bounds: concerns must focus on the real out-of-bounds point, decomposition_suggestions must be split according to functional boundaries,"
                "Do not output Skill Can only take numbers or All explanations belong to Agent This type of false premise.\n\n"
                "Please reply in JSON (no other content):\n"
                '{"within_boundary": true/false, "complexity_score": 1-5, '
                '"concerns": ["question 1", ...], "decomposition_suggestions": ["Suggestions 1", ...]}'
            )
        else:
            prompt = (
                "You are a Skill boundary detection expert. A Skill should focus on a clear and reusable functional unit."
                "It can include necessary data acquisition, cleaning and transformation, formatting, deterministic calculation, rule judgment or lightweight aggregation;"
                "But it should not carry open-ended research, subjective investment conclusions, or orchestration of long links across multiple independent goals.\n"
                f"{SKILL_SEMANTICS_GUIDANCE}\n\n"
                f"{SKILL_BOUNDARY_EXAMPLES}\n"
                "Are the following requirements beyond the scope of a single Skill?\n\n"
                f"demand: {user_message}\n\n"
                "If it is determined to be out of bounds: concerns must focus on the real out-of-bounds point, decomposition_suggestions must be split according to functional boundaries,"
                "Do not output Skill Can only take numbers or All explanations belong to Agent This type of false premise.\n\n"
                "Please reply in JSON (no other content):\n"
                '{"within_boundary": true/false, "complexity_score": 1-5, '
                '"concerns": ["question 1", ...], "decomposition_suggestions": ["Suggestions 1", ...]}'
            )
        try:
            response = client.chat([Message(role="user", content=prompt)])
            raw = response.content or "{}"
            logger.info(f"边界检测 LLM 原始返回 ({len(raw)} 字符):\n{raw}")
            data = self._parse_llm_json(raw)
            if data:
                return BoundaryCheck(**data)
        except Exception as e:
            logger.warning(f"边界检测失败: {e}")

        return BoundaryCheck()

    # ==================== Conversation building ====================

    @staticmethod
    def _get_max_rounds(clarity: Optional[ClarityLevel]) -> int:
        """根据清晰度决定对话轮数"""
        if clarity == ClarityLevel.HIGH:
            return 1
        elif clarity == ClarityLevel.MEDIUM:
            return 2
        return 3

    def _build_round1_response(self, session: SkillCreationSession, user_message: str) -> str:
        """Round 1: Initial Understanding + Disassembly of function points + Data source guidance"""
        catalog_context = self._build_catalog_context(user_message)
        handoff_context = self._build_handoff_context_text(session)
        handoff_guardrails = self._build_handoff_guardrails(session)
        prompt = (
            "你是 Skill 需求分析专家，不仅理解用户需求，更要主动给出专业建议。\n\n"
            "## Project background\n"
            "where you are **TradingAgents-CN**: A multi-agent stock analysis learning platform for Chinese users."
            "The platform focuses on compliance research and strategy experiments on A-shares/Hong Kong stocks/US stocks, and uses AI Agent to call various reusable Skills to complete analysis."
            "The Skill being created by the user will serve as a reusable functional tool that can be called by the Agent and can be used for clear and verifiable capabilities such as data acquisition, cleaning and transformation, indicator calculation, rule judgment, and structured summary."
            "Skill It doesn t mean you can only take numbers, but you should avoid cramming open-ended research, subjective investment conclusions, or complete multi-stage workflows into a single skill.\n\n"
            f"{SKILL_SEMANTICS_GUIDANCE}\n\n"
            f"{STANDARD_FINANCIAL_APIS_SUMMARY}\n\n"
            "## your task\n"
            "1. restate your understanding\n"
            "2. Use a table to list function points (target market, input parameters, return fields, calling methods)\n"
            "3. **Unsolicited suggestions**: Provide professional suggestions based on user needs (such as more suitable implementation methods, common pitfalls, best practices)\n"
            "4. **Implement path guidance (important)**: \n"
            "   - **first check**: Have the user requirements been covered by the functions in the Project built-in standard financial data capabilities above?\n"
            "   - If it has been covered: directly inform the user that the project has built-in this capability (XXX function), there is no need to select a data source, the data source is configured uniformly by the project ,"
            "And explain the return content and applicable scenarios of the function, without asking the data source.\n"
            "   - If not covered: Briefly explain that the project currently has no standard functions that are directly covered. It is recommended to implement it through the skill_runtime public interface combination."
            "or mention directions to external data sources that may be relevant, but**Don t let users choose data sources**——Data sources are configured and managed uniformly by the project.\n"
            "   - **Absolutely not**Asking users questions such as Do you prefer AKShare or Tushare? This is not something users should care about.\n\n"
            "5. Raise other issues that need to be confirmed (such as return format, risk judgment rules, batch requirements, etc.)\n\n"
            f"{handoff_guardrails}\n"
            f"Upstream handover context:\n{handoff_context or 'None'}\n\n"
            f"Data context currently hit on demand:\n{catalog_context}\n\n"
            f"User description: {user_message}"
        )
        try:
            content = self._chat_with_quick_fallback(
                [Message(role="user", content=prompt)], stage="第1轮需求分析"
            )
            if content:
                return content
            self._raise_analysis_error("第1轮需求分析")
        except Exception as e:
            logger.error(f"第1轮需求分析失败: {e}")
            self._raise_analysis_error("第1轮需求分析", e)

    def _build_iteration_round1_response(
        self,
        session: SkillCreationSession,
        user_message: str,
        skill_context: str,
    ) -> str:
        """Iterative mode round 1: Show the current status of existing skills and guide users to describe what needs to be adjusted"""
        prompt = (
            "You are a Skill iterative optimization expert. The user is optimizing an existing Skill. The following is the current Skill information:\n\n"
            f"```json\n{skill_context}\n```\n\n"
            "## your task\n"
            "Please use**minimalist**Reply in the following way, do not generate specifications, do not list function tables, and do not analyze data sources:\n\n"
            "**Step 1: Introduce the current situation in one sentence Skill**\n"
            "Tell users in plain language: what this Skill does, what it inputs, and what it outputs. Maximum 3 lines.\n\n"
            "**Step 2: Understand the user s improvement intentions and guide them**\n"
            "User said:" + user_message + "\n"
            "Based on the user s description, please determine which category his intention falls into (Bug fix/Function enhancement/Result optimization/Others),"
            "then**Ask only the 1-2 most critical confirmation questions**, Guide users to provide more specific directions for improvement.\n\n"
            "**Constraints:**\n"
            "- Do not generate tool specification confirmation (tool_id/parameters/return fields/data sources, etc.), leave those for later processes.\n"
            "- Don t ask about data source selection, don t list local collections, don t mention AKShare/Tushare\n"
            "- The core purpose of this reply: let the user confirm your understanding, and then provide more improvement details\n"
            "- If the user s idea completely conflicts with the current Skill implementation, we gently recommend re-creating it."
        )
        try:
            content = self._chat_with_quick_fallback(
                [Message(role="user", content=prompt)], stage="迭代模式第1轮需求分析"
            )
            if content:
                return content
            self._raise_analysis_error("迭代模式第1轮需求分析")
        except Exception as e:
            logger.error(f"The first round of requirements analysis in iterative mode failed: {e}")
            self._raise_analysis_error("迭代模式第1轮需求分析", e)

    def _build_round2_response(
        self, session: SkillCreationSession, user_message: str
    ) -> str:
        """Round 2: Technology Refinement"""
        history = self._collect_conversation(session, user_message)
        catalog_context = self._build_catalog_context(history)
        handoff_context = self._build_handoff_context_text(session)
        handoff_guardrails = self._build_handoff_guardrails(session)
        prompt = (
            "你是 Skill 需求分析专家，所在项目是 **TradingAgents-CN**（A股/港股/美股多智能体股票分析平台）。"
            "Round 2 of technical refinement is underway.\n\n"
            f"{STANDARD_FINANCIAL_APIS_SUMMARY}\n\n"
            "Please draw on previous conversations and new user feedback:\n"
            "1. Confirm technical solutions (return format, risk judgment rules, etc.)\n"
            "2. **Unsolicited suggestions**: Provide technical solution suggestions based on user needs (such as recommended implementation methods, boundary case handling)\n"
            "3. **Implement path confirmation**: Confirm whether user requirements are covered by the project s built-in standard functions."
            "If it has been covered, it indicates which function will be reused; if it is not covered, it indicates that it will be implemented through the skill_runtime public interface combination."
            "**Don t ask the user to select a data source**——Data sources are configured uniformly by the project.\n"
            "4. Give recommendations and let users choose (instead of asking open-ended questions)\n"
            "5. List the final list of parameters and return fields\n\n"
            f"{handoff_guardrails}\n"
            f"Upstream handover context:\n{handoff_context or 'None'}\n\n"
            f"Data context currently hit on demand:\n{catalog_context}\n\n"
            f"Conversation history:\n{history}"
        )
        try:
            content = self._chat_with_quick_fallback(
                [Message(role="user", content=prompt)], stage="第2轮需求分析"
            )
            if content:
                return content
            self._raise_analysis_error("第2轮需求分析")
        except Exception as e:
            logger.error(f"第2轮需求分析失败: {e}")
            self._raise_analysis_error("第2轮需求分析", e)

    def _build_spec_confirmation(
        self, session: SkillCreationSession, user_message: str
    ) -> str:
        """Final round: Generate specification validation summary"""
        history = self._collect_conversation(session, user_message)
        catalog_context = self._build_catalog_context(history)
        handoff_context = self._build_handoff_context_text(session)
        handoff_guardrails = self._build_handoff_guardrails(session)
        prompt = (
            "你是 Skill 需求分析专家，请根据所有对话内容生成最终的规格确认摘要。\n"
            "Output in the following format:\n"
            "## Skill Specification confirmation\n"
            "- **tool_id**: xxx\n"
            "- **Name**: xxx\n"
            "- **Description**: xxx\n"
            "- **Classification**: xxx\n"
            "- **data source**: xxx\n"
            "- **Recommended local collections for reuse**: list\n"
            "- **Recommend external sources**: List (if local is sufficient, it can be written as None or only as a source of downgrade)\n"
            "- **parameters**: list\n"
            "- **Return field**: list\n"
            "- **constraint**: list\n\n"
            "Requirements: Recommended reuse items must first reference collections and external sources that have been hit by the current system, and do not make up data sources that have not been sorted out in the system.\n\n"
            "Finally ask the user: 'Are the above specifications correct? Code generation will begin upon confirmation.'\n\n"
            f"{handoff_guardrails}\n"
            f"Upstream handover context:\n{handoff_context or 'None'}\n\n"
            f"Data context currently hit on demand:\n{catalog_context}\n\n"
            f"Conversation history:\n{history}"
        )
        try:
            content = self._chat_with_quick_fallback(
                [Message(role="user", content=prompt)], stage="规格确认摘要生成"
            )
            if content:
                return content
            self._raise_analysis_error("规格确认摘要生成")
        except Exception as e:
            logger.error(f"规格确认摘要生成失败: {e}")
            self._raise_analysis_error("规格确认摘要生成", e)

    @staticmethod
    def _build_boundary_warning(check: BoundaryCheck) -> str:
        """构建边界警告消息"""
        concerns = "\n".join(f"  - {c}" for c in check.concerns)
        suggestions = "\n".join(
            f"  {i+1}. {s}" for i, s in enumerate(check.decomposition_suggestions)
        )
        return (
            "⚠️ Your requirements include multiple functional levels. It is recommended to split them into:\n\n"
            f"**Focus:**\n{concerns}\n\n"
            f"**It is recommended to split it into:**\n{suggestions}\n\n"
            "Each Skill should focus on a clear function and can include necessary data acquisition and deterministic processing;"
            "Open analysis, investment conclusions and multi-stage orchestration are completed by Agent/Workflow.\n"
            "If your goal itself is a verifiable deterministic function, you can continue to converge into a single Skill instead of being forced to split it into Pure number layer . \n"
            "Please choose a clear unit of capability to start creating, or tell me which function you want to build first."
        )

    # ==================== conversation collection & Specification generation ====================

    @staticmethod
    def _collect_conversation(
        session: SkillCreationSession, current_message: str = ""
    ) -> str:
        """Collect all conversation history into formatted string"""
        parts = []
        handoff_context = RequirementAnalyzer._build_handoff_context_text(session)
        if handoff_context:
            parts.append(f"[系统交接上下文]:\n{handoff_context}")
        for r in session.rounds:
            parts.append(f"[用户 - 第{r.round_number}轮]: {r.user_message}")
            parts.append(f"[AI - 第{r.round_number}轮]: {r.ai_message}")
        if current_message:
            parts.append(f"[用户 - 最新]: {current_message}")
        return "\n\n".join(parts)

    def _generate_spec(
        self,
        conversation: str,
        fact_report: Optional[ImplementationFactReport] = None,
        session: Optional[SkillCreationSession] = None,
        parent_contract: Optional[Dict[str, Any]] = None,
    ) -> Optional[SkillSpec]:
        """Transform conversations into structures with LLM SkillSpec

        Args:
            conversation: Collected conversations
            fact_report: Recon report (recon-front mode) with true field availability
            session: Current session (used for iterative pattern recognition, the original tool_id and other version relationships will be retained when passed in)
            parent_contract: Parent version contract (service layer loading, including complete parameters/constraints/code).
                When passing in, priority is given to the upgrade patch mode (LLM only outputs delta, and the parent contract is deterministically inherited).
                When patch generation fails, it will be downgraded to full generation of the old version (parent contract constraints are injected into the prompt).
        """
        # Upgrade Patch Mode: Parent Contract + delta, Fields not mentioned have no output channels,
        # Structurally put an end to "reinventing parameter definitions/interface constraints" (it was once considered int=11 Rewritten as
        # The string "monthly sales list" causes the interface to silently fall back to the popular list, causing an endless loop of 4 attempts)
        if parent_contract:
            spec = self._generate_upgrade_spec(conversation, parent_contract)
            if spec:
                return spec
            logger.warning(
                "[UpgradePatch] Patch generation failed and was downgraded to full specification generation (parent contract context injected)"
            )

        # The essence of specification generation is structured transcription (the parameters/fields have been clearly confirmed in the dialogue),
        # Give priority to the fast model, and fall back to the main model if it fails.
        catalog_context = self._build_catalog_context(conversation)
        handoff_guardrails = ""
        if "[系统交接上下文]:" in conversation:
            handoff_guardrails = (
                "6. This session has an upstream handover context, and the upstream specification capabilities must be retained and not rewritten into another narrower, lazier implementation.\n"
                "7. If the original goal is obviously an Agent/Workflow level goal, the current SkillSpec can only be defined as one of the deterministic sub-abilities, and this should be made clear in description/constraints.\n"
                "8. It is forbidden to Valuation analysis  research analysis  multidimensional judgment This type of goal is directly replaced by a single PB/PE indicator calculator, unless the user explicitly only wants this sub-function.\n\n"
            )

        # 🔧 Iteration mode constraints: for new versions _v{N} Suffix, reflecting version relationship
        iteration_guardrails = ""
        is_iteration = bool(session and session.iterate_skill_id)
        if is_iteration:
            original_tool_id = session.iterate_skill_id or ""
            iteration_guardrails = (
                f"9. **Iteration mode constraints (must be adhered to)**: This time it is iterative optimization of the existing Skill. The tool_id of the original Skill is `{original_tool_id}`. \n"
                f"   - generated spec.tool_id **Must be `_v2`, `_v3` End with version suffix** (For first iteration `_v2`, For second iteration `_v3`, and so on).\n"
                f"   - **It is prohibited to use the original tool_id** (It will overwrite the original Skill and affect the old version bound to the Agent).\n"
                f"   - Naming format:`{{Original tool_id}}_v{{new version number}}`, Such as `{original_tool_id}_v2`. \n"
                f"   - display_name Must be ` v{{new version number}}` At the end, you can add a brief explanation, such as `xxx v2`. \n"
                f"   - This is an upgrade of the original Skill, not the creation of a new Skill; the functions should be improved on the basis of the original Skill, not completely overturned and rewritten.\n"
                f"   - Add one to constraints:`This Skill is {original_tool_id} iteratively optimized version of`. \n\n"
            )
            # Parent contract injection for downgrade paths: Even if fully generated, parameter definitions/interface constraints must be
            # The facts of multiple rounds of verification of the parent version shall prevail and shall not be reinvented.
            if parent_contract:
                iteration_guardrails += (
                    "10. **Parent version contract (a fact verified by multiple rounds of actual testing and must be inherited as is)**: \n"
                    f"```json\n{parent_contract_to_json(parent_contract)}\n```\n"
                    "    - Name/type/default value/value semantics and interface constraints of parameters with the same name (URL/request header/value requirements)"
                    "Must be exactly the same as the parent version, unless upgrade requirements explicitly require modification\n"
                    "    - Existing parameters and output fields of the parent version must not be lost\n\n"
                )

        # Reconnaissance fact injection: Inject real field availability and Helper function information prompt
        recon_context = ""
        if fact_report:
            recon_context = self._build_recon_context_for_spec(fact_report)

        prompt = (
            "You are the Skill Spec Generator. Please follow the dialogue below,"
            "Extract a structured Skill specification (JSON format).\n\n"
            "**important**: \n"
            "1. If there is [User - Latest]] Or the user clearly chooses the plan (such as choosing A/B/C), which must be generated strictly according to the user s choice and cannot be ignored.\n"
            "2. Skill Can be an explicit functional implementation, not limited to pure data query; allow necessary deterministic calculations, formatting and lightweight aggregation.\n"
            "3. data_source Fill in the primary data source ID identified in the dialog; if the implementation will combine closely related data sources, fill in the primary data source, and describe the additional source or downgrade strategy in constraints.\n"
            "4. Don t write vague descriptions such as needs to be passed in through parameters .\n\n"
            "5. Prioritize the spec to be consistent with the local collection and external sources that can be reused by the current system; if the local one can be satisfied, do not forcefully specify external sources.\n\n"
            "5.1 If this is a valuation class or method type Skill, expected_output.fields must first be close to the existing schema contract of the system, and do not create a set of field names.\n"
            "5.2 constraints The applicable boundaries, prohibited modes and necessary narrative requirements of the method should be clearly written rather than written in general terms.'Return valuation results'. \n\n"
            "6. **Naming rules (key)**: tool_id snake_case must be used, and **The same name as the underlying Python function referenced is prohibited**. \n"
            "   For example: if the implementation calls the get_stock_news function, the tool_id should be named get_unified_news or fetch_news_by_ticker,\n"
            "   It cannot also be called get_stock_news. Naming conflicts will cause infinite recursion during Skill execution.\n"
            "   Recommended naming format:get_<data source>_<Function> (Such as get_eastmoney_news, fetch_tushare_financials).\n\n"
            f"{handoff_guardrails}"
            f"{iteration_guardrails}"
            f"{SKILL_SEMANTICS_GUIDANCE}\n\n"
            f"Data context currently hit on demand:\n{catalog_context}\n\n"
        )

        # Insert recon fact context
        if recon_context:
            prompt += (
                f"### Implementation facts discovered by the reconnaissance layer (real data source detection results)\n"
                f"{recon_context}\n\n"
                "**Constraints based on reconnaissance facts**: \n"
                "- expected_output.fields Only include fields that are available through reconnaissance, and do not add fields based on your imagination that do not exist in the data source.\n"
                "- If the scouting context has provided financial schema methods/contracts/rules, expected_output.fields and constraints must be aligned with those schema objects in preference.\n"
                "- If a field has low coverage or is unavailable, the downgrade strategy should be noted in the constraints instead of being marked as required.\n"
                "- Prefer using helper functions discovered through reconnaissance rather than guessing at how API calls are made.\n\n"
            )

        prompt += f"对话内容:\n{conversation}\n\n"
        prompt += (
            "Please strictly use the following JSON format for output (no other content):\n"
            "Parameter naming rules (must be followed):\n"
            "- parameters name in must be a legal Python identifier (snake_case, such as month, rank_data_type)\n"
            "- HTTP Request headers (User-Agent/Referer/Token, etc.), authentication keys, and interface URLs are implementation details."
            "Write constraints (such as\"The request must carry User-Agent and Referer request headers\") , Strictly prohibited as a function parameter\n"
            "- parameters Only the business parameters that the caller needs to pass in (such as month, code, type) are included."
            "Hard-coded constants inside functions are not included\n\n"
            "{\n"
            '  "tool_id": "snake_case_id",\n'
            '  "display_name": "Chinese display name",\n'
            '  "description": "Function description",\n'
            '  "category": "news|market|fundamentals|social|technical|utility|valuation",\n'
            '  "data_source": "The data source identifier determined in the conversation",\n'
            '  "parameters": [\n'
            '    {"name": "param1", "type": "string", "description": "Description", '
            '"required": true}\n'
            "  ],\n"
            '  "expected_output": {\n'
            '    "type": "list[dict]",\n'
            '    "fields": ["field1", "field2"],\n'
            '    "description": "Output description"\n'
            "  },\n"
            '  "validation_checks": [\n'
            '    {"name": "status_success", "description": "Output status must be successful", "required": true, "check_type": "status_success", "rule_level": "output", "blocking": true, "value_path": "output", "forbid_null": false},\n'
            '    {"name": "required_field:field1", "description": "Field1 cannot be missing when output is successful.", "required": true, "check_type": "required_field", "rule_level": "data", "blocking": true, "field": "field1", "value_path": "data", "forbid_null": true}\n'
            "  ],\n"
            '  "constraints": ["constraint 1"],\n'
            '  "test_input": {"param1": "Test value"}\n'
            "}"
        )
        # JSON parsing with 1 retry
        max_attempts = 2
        last_raw = ""
        last_error: Optional[Exception] = None

        for attempt in range(max_attempts):
            try:
                if attempt == 0:
                    last_raw = self._chat_with_quick_fallback(
                        [Message(role="user", content=prompt)], stage="规格生成"
                    )
                else:
                    # The 2nd time: Feed back the last failed output to LLM and ask for correction.
                    retry_prompt = (
                        f"你上次的输出无法被解析为合法 JSON，请修正后重新输出。\n"
                        f"Last output:\n{last_raw[:8000]}\n\n"
                        f"Error: {last_error}\n\n"
                        "Please output only plain JSON, without any Markdown markup or explanatory text."
                    )
                    last_raw = self._chat_with_quick_fallback(
                        [
                            Message(role="user", content=prompt),
                            Message(role="assistant", content=last_raw[:8000]),
                            Message(role="user", content=retry_prompt),
                        ],
                        stage="规格生成",
                    )

                logger.info(f"SkillSpec LLM 原始返回 (attempt {attempt + 1}/{max_attempts}, {len(last_raw)} 字符):\n{last_raw}")
                data = self._parse_llm_json(last_raw)
                if data:
                    self._sanitize_spec_params(data)
                    self._ensure_interface_spec_constraints(data, conversation)
                    return self._ensure_spec_validation_checks(SkillSpec(**data))

                last_error = ValueError("LLM Not returned legal JSON")
                logger.warning(f"SkillSpec JSON Parsing failed (attempt {attempt + 1}/{max_attempts}): {last_error}")

            except Exception as e:
                last_error = e
                logger.warning(f"SkillSpec generate exception (attempt {attempt + 1}/{max_attempts}): {e}")

        logger.error(f"SkillSpec Build ultimately fails: {last_error}")
        self._raise_analysis_error("SkillSpec 生成", last_error)
        return None

    def _generate_upgrade_spec(
        self, conversation: str, parent_contract: Dict[str, Any]
    ) -> Optional[SkillSpec]:
        """Upgrade patch mode: LLM read parent contract + Only delta is output after the parent code, and it is deterministically applied to the new spec.

        The essential difference from full specification generation (aligned programming agent s edit-apply):
        - LLM The output channel only has change list and no parameters/constraints/fields mentioned
          Inherited unchanged from parent version by apply_upgrade_patch——There is no way to rewrite it
        - The parent code is fully injected (without truncation) to meet the understand the original code first and then read the new requirements 

        Returns:
            SkillSpec after applying the patch; failure to patch generation/application returns None (caller downgraded)
        """
        prompt = build_upgrade_patch_prompt(parent_contract, conversation)
        last_raw = ""
        last_error: Optional[Exception] = None

        for attempt in range(2):
            try:
                if attempt == 0:
                    last_raw = self._chat_with_quick_fallback(
                        [Message(role="user", content=prompt)], stage="升级补丁生成"
                    )
                else:
                    retry_prompt = (
                        f"你上次的输出无法解析为补丁 JSON，请修正后重新输出。\n"
                        f"Last output:\n{last_raw[:6000]}\n\n"
                        f"Error: {last_error}\n\n"
                        "Please output only plain JSON, without any Markdown markup or explanatory text."
                    )
                    last_raw = self._chat_with_quick_fallback(
                        [
                            Message(role="user", content=prompt),
                            Message(role="assistant", content=last_raw[:6000]),
                            Message(role="user", content=retry_prompt),
                        ],
                        stage="升级补丁生成",
                    )

                logger.info(
                    f"[UpgradePatch] 补丁 LLM 原始返回 (attempt {attempt + 1}/2, "
                    f"{len(last_raw)} character):\n{last_raw}"
                )
                patch = self._parse_llm_json(last_raw)
                if not isinstance(patch, dict):
                    raise ValueError("Patches must be JSON objects")
                spec = apply_upgrade_patch(parent_contract, patch)
                logger.info(
                    "[UpgradePatch] Patch applied successfully: tool_id=%s change point=%s",
                    spec.tool_id,
                    spec.metadata.get("upgrade_change_points"),
                )
                return spec
            except Exception as e:
                last_error = e
                logger.warning(f"[UpgradePatch] 第 {attempt + 1}/2 次失败: {e}")

        logger.error(f"[UpgradePatch] Patch generation ultimately fails: {last_error}")
        return None

    @staticmethod
    def _sanitize_spec_params(data: Dict[str, Any]) -> None:
        """Clean spec parameters: Remove illegal Python identifier parameters (such as headers.User-Agent).

        LLM HTTP request headers may be mistakenly included as function parameters; such names cannot appear in functions
        Signing will directly lead to an infinite loop of static verification. After elimination, add the header requirements into constraints.
        Ensure that implementation information is not lost.
        """
        import keyword as _keyword
        import re as _re

        def _usable(name: str) -> bool:
            return bool(_re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", name)) and not _keyword.iskeyword(name)

        params = data.get("parameters")
        if not isinstance(params, list):
            return
        valid = []
        dropped: list[str] = []
        for p in params:
            if isinstance(p, dict) and _usable(str(p.get("name") or "")):
                valid.append(p)
            elif isinstance(p, dict):
                dropped.append(str(p.get("name") or "未命名"))
        if dropped:
            data["parameters"] = valid
            constraints = data.get("constraints")
            if not isinstance(constraints, list):
                constraints = []
            constraints.append(
                f"Implementation details such as HTTP headers/authentication required for the request (original parameters: {', '.join(dropped)}) "
                "It should be hard-coded inside the function and not exposed as function parameters."
            )
            data["constraints"] = constraints
            logger.warning(f"[RequirementAnalyzer] Illegal identifier parameters have been removed: {dropped}")

    @staticmethod
    def _ensure_interface_spec_constraints(data: Dict[str, Any], conversation: str) -> None:
        """Extract interface specifications (URL/methods/request headers) from the original conversation text and write back the constraints in full.

        Background: The URL, request header, and parameter description given by the user in the external interface requirement are part of the interface contract.
        sole source of truth, but specification generation LLM may have its summary missing (constraints is empty),
        Causes the code generation phase to invent URLs (such as writing rank_data as rank/data → 404) . 
        """
        import re as _re

        if not conversation:
            return
        # Extract the words that appear in the conversation http(s) URL; The query string is an example parameter (should be implemented as a function parameter),
        # Only keep the base URL as a verbatim contract to avoid inducing LLM to hardcode example parameters.
        # The query string is retained solely as a "documented query parameter" constraint——It is interface preflight differential test
        # The basis for distinguishing "interface real parameters" and "business filtering parameters" (such as brand_name).
        # URL Matching is limited to ASCII URL characters: Chinese characters must be truncated when closely following the URL (such as "rank_data initiated")
        urls: list[str] = []
        url_queries: dict[str, str] = {}
        for m in _re.finditer(r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", conversation):
            raw = m.group(0)
            base_url = raw.split("?")[0].rstrip(".,;:")
            if base_url not in urls:
                urls.append(base_url)
            query = raw.split("?", 1)[1].rstrip(".,;:") if "?" in raw else ""
            if query and base_url not in url_queries:
                url_queries[base_url] = query
        if not urls:
            return

        constraints = data.get("constraints")
        if not isinstance(constraints, list):
            constraints = []
        existing = "\n".join(str(c) for c in constraints)

        added: list[str] = []
        for base_url in urls:
            if base_url in existing:
                continue
            constraints.insert(
                0,
                f" [Interface specifications — The interface must be used as is URL: {base_url} (Based on user requirements, the path/parameter name is strictly prohibited to be rewritten."
                "For example, rank_data must not be written as rank/data; the query parameters in the URL are only examples, and the parameters are passed as function parameters during implementation)",
            )
            added.append(base_url)

        # Documented query parameters: user URL original query string (idempotent: if it already exists, it will not be written repeatedly)
        query_added = 0
        for base_url, query in url_queries.items():
            if query in existing:
                continue
            constraints.insert(
                1,
                f" [Interface specifications] Interface query parameters (user URL original query string): {query}"
                "——Only these parameters are the real query parameters of the interface and can be assembled into URL requests;"
                "Other business filtering conditions (such as brand/manufacturer) are not supported by the interface. The data must be pulled and filtered locally based on the return field.",
            )
            query_added += 1

        # Request header requirements
        header_kws = ["User-Agent", "Referer", "Authorization", "Content-Type", "Token", "请求头"]
        mentioned_headers = [kw for kw in header_kws if kw in conversation]
        if mentioned_headers and "请求头" not in existing and "User-Agent" not in existing:
            constraints.insert(
                1,
                f"【接口规格】请求需携带请求头: {'、'.join(dict.fromkeys(mentioned_headers))}（以用户需求描述为准）",
            )

        if added or query_added or mentioned_headers:
            data["constraints"] = constraints
            logger.warning(
                f"[RequirementAnalyzer] The interface specification was detected in the conversation and has been written down in detail. constraints: urls={added}, "
                f"queries={query_added}, headers={mentioned_headers[:4]}"
            )

    @staticmethod
    def _build_recon_context_for_spec(report: ImplementationFactReport) -> str:
        """Convert recon report to spec to generate prompt consumable text context."""
        parts = []

        if report.recommended_strategy:
            parts.append(f"- 推荐实现策略: {report.recommended_strategy}")

        if report.confidence:
            parts.append(f"- 侦察置信度: {report.confidence:.0%}")

        # Available Helper functions
        if report.available_helpers:
            helper_lines = []
            helper_field_names: set[str] = set()
            for h in report.available_helpers:
                sig = f"  • {h.name}({h.signature})" if h.signature else f"  • {h.name}"
                ds = h.data_source_handling or "self_contained"
                sig += f" [数据源:{ds}]"
                if h.description:
                    sig += f" — {h.description}"
                helper_lines.append(sig)
                # 🔧 Extract field names from the helper's Returns document, used to constrain LLM output field naming
                if h.description:
                    field_names = RequirementAnalyzer._extract_return_field_names(h.description)
                    helper_field_names.update(field_names)
            parts.append(
                "- Available Helper functions (data source: self_contained=self contained; local_only=local only MongoDB; partial=partial coverage):\n"
                + "\n".join(helper_lines)
            )
            # 🔧 Inject the field name actually returned by the helper to prevent LLM from creating its own field name
            if helper_field_names:
                sorted_fields = sorted(helper_field_names)
                parts.append(
                    f"- 🚨 Helper The actual returned field names (expected_output.fields must give priority to using these field names, no own creation is allowed): "
                    f"{', '.join(sorted_fields[:30])}"
                )

        # Database field live
        if report.schema_facts:
            fact_lines = []
            for f in report.schema_facts:
                # field/description To add optional fields, fall back to fact
                label = f.field if f.field else f.fact
                desc = f.description if f.description else ""
                line = f"  • [{f.source}] {label}"
                if desc:
                    line += f": {desc}"
                if f.coverage is not None:
                    line += f" (覆盖率 {f.coverage:.0%})"
                fact_lines.append(line)
            parts.append("- 数据库字段实况:\n" + "\n".join(fact_lines))

        # sample field
        if report.sample_fields:
            for collection, fields in report.sample_fields.items():
                parts.append(f"- {collection} 的实际字段: {', '.join(fields[:20])}")

        schema_bundle_context = report.schema_bundle_context or {}
        method = schema_bundle_context.get("method") or {}
        contract = schema_bundle_context.get("contract") or {}
        verifier_rule = schema_bundle_context.get("verifier_rule") or {}
        applicability_rules = schema_bundle_context.get("applicability_rules") or {}
        schema_lines = []
        if method:
            schema_lines.append(
                f"  • 方法: {method.get('name') or schema_bundle_context.get('method_id')}"
            )
            if method.get("required_fields"):
                schema_lines.append(
                    f"  • 方法前置字段: {', '.join(list(method.get('required_fields') or [])[:6])}"
                )
        if contract:
            contract_fields = [
                str((item or {}).get("field_name") or "").strip()
                for item in contract.get("required_fields") or []
                if str((item or {}).get("field_name") or "").strip()
            ]
            if contract_fields:
                schema_lines.append(f"  • 输出契约字段: {', '.join(contract_fields[:8])}")
        if applicability_rules:
            schema_lines.append(
                "  • 适用性规则: "
                + "；".join(
                    str((rule or {}).get("human_description") or rule_id)
                    for rule_id, rule in list(applicability_rules.items())[:4]
                )
            )
        if verifier_rule and verifier_rule.get("failure_message"):
            schema_lines.append(f"  • 验收失败语义: {verifier_rule.get('failure_message')}")
        if schema_lines:
            parts.append("- Financial schema guide:\n" + "\n".join(schema_lines))

        # blocked path
        if report.blocked_paths:
            block_lines = [f"  ⚠️ [{b.severity}] {b.path}: {b.reason}" for b in report.blocked_paths]
            parts.append("- 受阻路径（不可用）:\n" + "\n".join(block_lines))

        # runtime gap
        if report.runtime_gaps:
            gap_lines = [f"  ⚠️ [{g.severity}] {g.path}: {g.reason}" for g in report.runtime_gaps]
            parts.append("- 运行时缺口:\n" + "\n".join(gap_lines))

        if report.notes:
            parts.append("- 备注: " + "; ".join(report.notes))

        return "\n".join(parts) if parts else ""

    @staticmethod
    def _extract_return_field_names(description: str) -> list[str]:
        """Extract the field names listed in the Returns block from the helper s docstring description.

        Helper The docstring usually contains a Returns paragraph like this:
            Returns:
                dict: Field description (used in code .get() or [] access these keys)——
                    status: Status: "success" | "no_pledge" | ...
                    symbol: Standardized 6-digit stock code
                    metrics: aggregated metrics — ...
                    top_pledgers: List of top undeposited shareholders
                    ...

        This method parses out field names such as status / symbol / metrics / top_pledgers,
        Used to constrain the spec generation phase not to create your own field names.
        """
        if not description:
            return []
        text = str(description)

        # Locate the Returns block
        returns_idx = text.find("Returns:")
        if returns_idx < 0:
            return []
        returns_block = text[returns_idx:]

        # Cut to next paragraph mark (Args/Examples/Note, etc.) or end of document
        for marker in ("\nArgs:", "\nExamples:", "\nNote:", "\nRaises:"):
            marker_idx = returns_block.find(marker)
            if marker_idx > 0:
                returns_block = returns_block[:marker_idx]
                break

        field_names: list[str] = []
        seen: set[str] = set()
        # match "            field_name: Description" This kind of business
        # Field names usually consist of letters/numbers/underscores, preceded by a colon
        import re
        for match in re.finditer(r"^\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*:", returns_block, re.MULTILINE):
            name = match.group(1)
            # Filter out obvious non-field names (such as "dict", "list", "str", "Returns" etc.)
            if name.lower() in {"dict", "list", "str", "int", "float", "bool", "returns", "args", "examples", "note"}:
                continue
            if name in seen:
                continue
            seen.add(name)
            field_names.append(name)
        return field_names
