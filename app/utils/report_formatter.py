"""
Unified research report formatting tool

Provides unified report extraction and formatting functions for use by SimpleAnalysisService and UnifiedAnalysisService.
Make sure the report format is consistent and contains all necessary fields:
- Macro report: index_report (market research), sector_report (Industry sector research)
- Basic report:market_report, sentiment_report, news_report, fundamentals_report
- Research conclusion:investment_plan, trader_investment_plan, final_trade_decision
- Research team:bull_researcher, bear_researcher, research_team_decision
- Risk Team:risky_analyst, safe_analyst, neutral_analyst, risk_management_decision
"""

import logging
import uuid
import json
import re
from typing import Dict, Any, Optional, Tuple

from app.utils.compliance import normalize_research_brief_lists, sanitize_display_report_text, sanitize_report_artifacts

logger = logging.getLogger(__name__)
_ERROR_RESULT_PATTERNS = (
    re.compile(r'^\{[\s\S]*["\']error["\']\s*:\s*["\'][\s\S]*["\']\s*,\s*["\']success["\']\s*:\s*False[\s\S]*\}$'),
    re.compile(r'^Execution failed[:: ].*$', re.IGNORECASE),
)

def _build_report_failure_fallback(report_type: str) -> str:
    fallback_map = {
        "risk": "The execution of the risk review module has not been completed, and the current risk conclusions still need to be verified.",
        "investment": "The implementation of the comprehensive research conclusion module has not been completed, and the current conclusions still need to be verified.",
        "final_decision": "The implementation of the comprehensive research conclusion module has not been completed, and the current conclusions still need to be verified.",
    }
    return fallback_map.get(report_type, "Tool execution or model generation has not been completed, and the current conclusions still need to be verified.")


def _is_error_payload_text(content: str) -> bool:
    stripped = (content or "").strip()
    if not stripped:
        return False
    return any(pattern.match(stripped) for pattern in _ERROR_RESULT_PATTERNS)
    logger.info(f"🔄 [JSON Convert] Start conversion, report type: {report_type}, content length: {len(content) if content else 0}")

    if _is_error_payload_text(content):
        logger.warning(f"⚠️ [JSON Convert] Error payload text detected, returned by downgrade copy, report type: {report_type}")
        return _build_report_failure_fallback(report_type)


DISPLAY_SANITIZED_REPORT_KEYS = {
    'bull_researcher',
    'bull_report',
    'bear_researcher',
    'bear_report',
    'research_team_decision',
    'investment_plan',
    'trader_investment_plan',
    'risky_analyst',
    'risky_opinion',
    'safe_analyst',
    'safe_opinion',
    'neutral_analyst',
    'neutral_opinion',
    'risk_management_decision',
}


# All standard reporting fields
STANDARD_REPORT_FIELDS = [
    # 🆕 Macro research reports (priority for display)
    'index_report',           # Market/index analysis
    'sector_report',          # Industry/sector analysis
    # Individual stock research reports
    'market_report',          # Market technical analysis
    'sentiment_report',       # Social media sentiment analysis
    'news_report',            # Journalism Research
    'fundamentals_report',    # fundamental analysis
    'chip_report',            # Chip distribution analysis
    # research conclusion report
    # 'investment_plan',        # Research Manager Conclusion (as an alternative to research_team_decision)
    'trader_investment_plan', # Research and integrate opinions
    'research_team_decision', # Research team conclusion
    'risk_management_decision', # Risk review conclusion
    'final_trade_decision'    # Comprehensive research conclusion
]


def _failure_shape_message(value: dict) -> Optional[str]:
    """🛡️ Q1: Identifies a failed/empty response wrapper dict and returns a user-friendly prompt (returns None for non-failure forms).

    Cover {'success': False, 'error': ...} (Node exception) and
    {'content': '', 'success': True} (Empty response is packaged as success) two categories.
    """
    if not isinstance(value, dict):
        return None
    content_val = value.get("content")
    if value.get("success") is False or (
        value.get("success") is True
        and not (isinstance(content_val, str) and content_val.strip())
    ):
        err = value.get("error") or "Model response exception (empty content)"
        return f"> ⚠️ **Generation of this section failed**: {err}. It is recommended to reanalyze to get the full report."
    return None


def _extract_report_text(report_key: str, value: Any) -> Optional[str]:
    text_value = None

    if isinstance(value, str):
        text_value = value.strip()
    elif isinstance(value, dict):
        # 🛡️ Q1: Failure/empty response form → Render friendly prompt instead of skipping (naked dict is strictly prohibited from reporting)
        _failure_msg = _failure_shape_message(value)
        if _failure_msg:
            logger.warning(f"⚠️ [ReportFormatter] {report_key} For failure/empty response form, render prompt")
            return _failure_msg
        for key in ("content", "markdown", "text", "message", "report"):
            nested_value = value.get(key)
            if isinstance(nested_value, str) and nested_value.strip():
                text_value = nested_value.strip()
                break
    elif value is not None:
        raw_text = str(value).strip()
        if raw_text:
            text_value = raw_text

    if not text_value or len(text_value) <= 10:
        return None

    if report_key == 'final_trade_decision':
        return _convert_json_to_markdown(text_value, "final_decision")
    if report_key == 'research_team_decision':
        return _convert_json_to_markdown(text_value, "final_decision")
    if report_key == 'risk_management_decision':
        return _convert_json_to_markdown(text_value, "risk")
    return _clean_report_for_display(report_key, text_value)


def _extract_reports_from_mapping(mapping: Dict[str, Any], reports: Dict[str, str], source_name: str) -> None:
    if not isinstance(mapping, dict):
        return

    logger.info(f"🔍 [ReportFormatter] {source_name} Field: {list(mapping.keys())}")

    for field in STANDARD_REPORT_FIELDS:
        if field in reports:
            continue
        extracted = _extract_report_text(field, mapping.get(field))
        if extracted:
            reports[field] = extracted
            logger.info(f"📊 [ReportFormatter] Extract report: {field} <- {source_name} - length: {len(extracted)}")

    for report_key in DISPLAY_SANITIZED_REPORT_KEYS:
        if report_key in reports:
            continue
        extracted = _extract_report_text(report_key, mapping.get(report_key))
        if extracted:
            reports[report_key] = extracted
            logger.info(f"📊 [ReportFormatter] Extract report: {report_key} <- {source_name} - length: {len(extracted)}")


def extract_reports_from_state(state: Any) -> Dict[str, str]:
    """
    Extract all report content from state

    Args:
        state: Parse state object (can be a dictionary or object)

    Returns:
        Dictionary containing all reports
    """
    reports = {}

    if state is None:
        return reports

    nested_reports = _get_field_value(state, 'reports')
    has_nested_reports = isinstance(nested_reports, dict) and bool(nested_reports)

    if has_nested_reports:
        _extract_reports_from_mapping(nested_reports, reports, 'state.reports')

    # 🔥 Debug log: display top-level fields of state
    if isinstance(state, dict):
        logger.info(f"🔍 [ReportFormatter] state Top level fields: {list(state.keys())}")
        # 🔥 Check whether index_report and sector_report exist
        if "index_report" in state:
            logger.info(f"🔍 [ReportFormatter] index_report existence, length: {len(str(state.get('index_report', '')))}")
        elif not has_nested_reports:
            logger.warning(f"⚠️ [ReportFormatter] index_report Field does not exist in state")
        if "sector_report" in state:
            logger.info(f"🔍 [ReportFormatter] sector_report existence, length: {len(str(state.get('sector_report', '')))}")
        elif not has_nested_reports:
            logger.warning(f"⚠️ [ReportFormatter] sector_report Field does not exist in state")

    # 1. Extract report fields (first read from structured_reports output by the engine, automatically include new agent output)
    structured_reports = _get_field_value(state, 'structured_reports')
    if isinstance(structured_reports, dict) and structured_reports:
        for field, entry in structured_reports.items():
            if field in reports:
                continue
            if isinstance(entry, dict) and entry.get("success") and entry.get("content"):
                content = entry["content"]
                if isinstance(content, str) and len(content.strip()) > 10:
                    reports[field] = content.strip()
                    logger.info(f"📊 [ReportFormatter] Extracted from structured_reports: {field} - length: {len(content.strip())}")
    else:
        # Fallback: derivation from report_manifest
        manifest = _get_field_value(state, 'report_manifest')
        if isinstance(manifest, list) and manifest:
            for m in manifest:
                field = m.get("field")
                if field and field not in reports:
                    value = _get_field_value(state, field)
                    extracted = _extract_report_text(field, value)
                    if extracted:
                        reports[field] = extracted
                        logger.info(f"📊 [ReportFormatter] Extract from manifest: {field} - length: {len(extracted)}")
        else:
            # Final fallback: legacy hardcoded lists
            for field in STANDARD_REPORT_FIELDS:
                if field in reports:
                    continue
                value = _get_field_value(state, field)
                extracted = _extract_report_text(field, value)
                if extracted:
                    reports[field] = extracted
                    logger.info(f"📊 [ReportFormatter] Extract from hardcoded list: {field} - length: {len(extracted)}")

    # 2. Extract the research team debate status report (investment_debate_state)
    debate_state = _get_field_value(state, 'investment_debate_state')
    if debate_state:
        _extract_investment_debate_reports(debate_state, reports)
    else:
        logger.warning("⚠️ [ReportFormatter] investment_debate_state Does not exist or is empty")

    # 3. Extract the risk management team debate status report (risk_debate_state)
    risk_state = _get_field_value(state, 'risk_debate_state')
    if risk_state:
        _extract_risk_debate_reports(risk_state, reports)
    else:
        logger.warning("⚠️ [ReportFormatter] risk_debate_state Does not exist or is empty")

    # 🔥 Alternative: Find directly from top-level state bull_report, bear_report etc fields
    # New workflows may store reports in different locations
    _extract_alternative_reports(state, reports)

    logger.info(f"📊 [ReportFormatter] Extract to {len(reports)} reports: {list(reports.keys())}")
    return reports


def _clean_report_for_display(report_key: str, text: str) -> str:
    cleaned_text = _remove_author_signature(text.strip())
    artifact_cleaned_text = sanitize_report_artifacts(cleaned_text)
    if artifact_cleaned_text:
        cleaned_text = artifact_cleaned_text
    elif any(token in cleaned_text for token in ("</tool_call>", "<tool_call", '"name": "get_')):
        if report_key == 'news_report':
            return "The tool results were not successfully expanded into news reports, and the current news conclusions still need to be verified."
        return "The tool results were not successfully expanded into text, and the current conclusions still need to be verified."

    if report_key in DISPLAY_SANITIZED_REPORT_KEYS:
        cleaned_text = sanitize_display_report_text(cleaned_text, fallback=cleaned_text)
    return cleaned_text


def _extract_alternative_reports(state: Any, reports: Dict[str, str]):
    """
    Alternative: Pull the report from the state top level or elsewhere

    New workflows may store reports in different locations, such as:
    - bull_report (instead of investment_debate_state.bull_history)
    - bear_report (instead of investment_debate_state.bear_history)
    """
    # Alternative field mapping (including v2.0 agent field)
    alternative_mappings = {
        'bull_researcher': ['bull_report', 'bull_history', 'bull_analysis'],
        'bear_researcher': ['bear_report', 'bear_history', 'bear_analysis'],
        'neutral_analyst': ['neutral_report', 'neutral_history', 'neutral_analysis'],
        'trader_investment_plan': ['trader_investment_plan', 'trading_plan', 'trade_plan'],
        # 🔥 research_team_decision Can be read from the investment_plan field (some workflows are stored here)
        'research_team_decision': ['research_team_decision', 'investment_plan', 'investment_advice', 'judge_decision'],
        'risk_management_decision': ['risk_management_decision', 'risk_assessment', 'judge_decision'],
        'final_trade_decision': ['final_trade_decision'],
        # 🔥 Remove investment_plan as a separate field (to avoid confusion with trader_investment_plan)
        # 'investment_plan': ['investment_plan', 'investment_advice'],
        # v2.0 Risk Analyst Field Mapping
        'risky_analyst': ['risky_analyst', 'risky_opinion', 'risky_history'],
        'safe_analyst': ['safe_analyst', 'safe_opinion', 'safe_history'],
        'neutral_analyst': ['neutral_analyst', 'neutral_opinion', 'neutral_history'],
    }

    for report_key, alt_fields in alternative_mappings.items():
        if report_key in reports:
            continue  # Already extracted

        for alt_field in alt_fields:
            value = _get_field_value(state, alt_field)
            text_value = None
            if isinstance(value, str):
                text_value = value.strip()
            elif isinstance(value, dict):
                # 🛡️ Q1: Failure/empty response form → Rendering-friendly tips (naked dict is strictly prohibited from entering reports)
                _failure_msg = _failure_shape_message(value)
                if _failure_msg:
                    logger.warning(
                        f"⚠️ [ReportFormatter] alternative extraction {report_key} <- {alt_field} For failure/empty response form, render prompt"
                    )
                    reports[report_key] = _failure_msg
                    break
                for k in ("content", "markdown", "text", "message", "report"):
                    v = value.get(k)
                    if isinstance(v, str) and v.strip():
                        text_value = v.strip()
                        break
            if text_value and len(text_value) > 10:
                # 🔥 For fields that may contain JSON, convert to Markdown
                if report_key == 'final_trade_decision':
                    markdown_value = _convert_json_to_markdown(text_value, "final_decision")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                elif report_key == 'research_team_decision':
                    # Research team conclusions may also be in JSON format
                    logger.info(f"🔍 [ReportFormatter] Alternative extraction detected research_team_decision, ready for conversion JSON")
                    logger.info(f"🔍 [ReportFormatter] First 500 characters of original content: {text_value[:500]}")
                    markdown_value = _convert_json_to_markdown(text_value, "final_decision")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                    logger.info(f"📊 [ReportFormatter] The first 500 characters of the converted content: {markdown_value[:500]}")
                elif report_key == 'risk_management_decision':
                    # Risk management decisions may also be in JSON format
                    markdown_value = _convert_json_to_markdown(text_value, "risk")
                    reports[report_key] = markdown_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Converted JSON->Markdown)")
                else:
                    # 🔥 Clean up signature information generated by AI
                    cleaned_value = _clean_report_for_display(report_key, text_value)
                    reports[report_key] = cleaned_value
                    logger.info(f"📊 [ReportFormatter] alternative extraction: {report_key} <- {alt_field} (Signature cleared)")
                break


def _get_field_value(obj: Any, field: str) -> Any:
    """Safely get field values"""
    if obj is None:
        return None
    if hasattr(obj, field):
        return getattr(obj, field, None)
    elif isinstance(obj, dict) and field in obj:
        return obj[field]
    return None


def _convert_json_to_markdown(content: str, report_type: str = "investment") -> str:
    """
    Convert JSON formatted report to Markdown format

    Args:
        content: Report content (may be a JSON string or plain text)
        report_type: Report Type ("investment", "risk" or "final_decision") 

    Returns:
        Markdown Format report content
    """
    logger.info(f"🔄 [JSON Convert] ========== Start converting ==========")
    logger.info(f"🔄 [JSON Convert] report type: {report_type}")
    logger.info(f"🔄 [JSON Convert] content length: {len(content) if content else 0}")
    logger.info(f"🔄 [JSON Convert] Content type: {type(content)}")

    if not content or not isinstance(content, str):
        logger.warning(f"⚠️ [JSON Convert] If the content is empty or not a string, it will be returned directly.")
        return content

    content = content.strip()
    logger.info(f"🔄 [JSON Convert] The first 500 characters of the content: {content[:500]}")
    logger.info(f"🔄 [JSON Convert] Does it contain '```json': {'```json' in content}")
    logger.info(f"🔄 [JSON Convert] Whether to {{ Beginning: {content.startswith('{')}")

    if _is_error_payload_text(content):
        logger.warning(f"⚠️ [JSON Convert] Error payload text detected, returned by downgrade copy, report type: {report_type}")
        return _build_report_failure_fallback(report_type)

    # Check if it is in JSON format
    json_obj = None

    # 1. Try to extract JSON code block
    if "```json" in content:
        logger.info(f"🔄 [JSON Convert] JSON code block detected")
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
            logger.info(f"🔄 [JSON Convert] Extracted JSON string length: {len(json_str)}, first 200 characters: {json_str[:200]}")
            
            # 🔥 Fix common JSON format issues
            # 1. Repair price_analysis_range: 295.29-442.93 -> [295.29, 442.93]
            # match pattern: "price_analysis_range": numbers - numbers
            json_str = re.sub(
                r'"price_analysis_range"\s*:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',
                r'"price_analysis_range": [\1, \2]',
                json_str
            )
            
            try:
                json_obj = json.loads(json_str)
                logger.info(f"✅ [JSON Convert] JSON Code block parsed successfully, field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
            except json.JSONDecodeError as e:
                logger.warning(f"⚠️ [JSON Convert] JSON Code block parsing failed: {e}")
                # If it still fails after repairing, record the repaired content for debugging
                logger.debug(f"🔍 [JSON Convert] The first 500 characters of the repaired JSON string: {json_str[:500]}")

    # 2. Try to parse directly JSON
    if json_obj is None and content.startswith("{"):
        logger.info(f"🔄 [JSON Convert] Detected with {{ At the beginning, try to parse directly JSON")
        # 🔥 Fix common JSON format issues
        fixed_content = re.sub(
            r'"price_analysis_range"\s*:\s*(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',
            r'"price_analysis_range": [\1, \2]',
            content
        )
        try:
            json_obj = json.loads(fixed_content)
            logger.info(f"✅ [JSON Convert] Direct JSON parsing successful, field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ [JSON Convert] Direct JSON parsing failed: {e}")

    # If it is not JSON, return the original content directly.
    if json_obj is None:
        logger.warning(f"⚠️ [JSON Convert] It is not in JSON format and returns the original content directly.")
        logger.warning(f"⚠️ [JSON Convert] The first 1000 characters of the original content: {content[:1000]}")
        return content

    # Convert to Markdown
    logger.info(f"🔄 [JSON Convert] Start converting to Markdown, report type: {report_type}")
    logger.info(f"🔄 [JSON Convert] JSON object field: {list(json_obj.keys()) if isinstance(json_obj, dict) else 'N/A'}")

    if report_type == "investment":
        result = _convert_investment_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] Research conclusion conversion completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    elif report_type == "risk":
        result = _convert_risk_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] Risk assessment conversion completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    elif report_type == "final_decision":
        result = _convert_final_decision_json_to_markdown(json_obj)
        logger.info(f"✅ [JSON Convert] The final research conclusion conversion is completed, Markdown length: {len(result)}")
        logger.info(f"✅ [JSON Convert] Markdown first 500 characters: {result[:500]}")
        return result
    else:
        logger.warning(f"⚠️ [JSON Convert] Unknown report type: {report_type}, Return directly to the original content")
        return content


def _convert_investment_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """Convert research conclusion JSON to Markdown"""
    logger.info(f"🔄 [Conversion of research conclusions] JSON Field: {list(json_obj.keys())}")
    lines = []
    
    # Summary of Research Perspectives
    action = json_obj.get("analysis_view") or json_obj.get("action", "")
    logger.info(f"🔄 [Conversion of research conclusions] action: {action}")
    if action:
        action_map = {
            # New compliance terms (optimistic/cautious/neutral) take precedence
            "optimistic": "🟢 optimistic",
            "Prudence": "🟡 Prudence",
            "Neutral": "⚪ Neutral",
            # old market view terminology + Old transaction instructions (compatible with existing data, mapped to new compliance expressions)
            "buy": "🟢 optimistic",
            "hold": "⚪ Neutral",
            "sell": "🟡 Prudence",
            "bullish": "🟢 optimistic",
            "Bearish": "🟡 Prudence",
        }
        action_display = action_map.get(action, action)
        lines.append(f"## 💡 research perspective\n\n**point of view**: {action_display}\n\n")
    
    # Confidence
    confidence = json_obj.get("confidence")
    logger.info(f"🔄 [Conversion of research conclusions] confidence: {confidence}")
    if confidence is not None:
        # 🔥 Fix: handle both 0-1 decimal and 0-100 integer situations
        try:
            conf_value = float(confidence)
            # If it is a decimal between 0 and 1, convert it to a percentage
            if conf_value <= 1:
                conf_display = int(conf_value * 100)
            else:
                conf_display = int(conf_value)
            lines.append(f"**Confidence**: {conf_display}/100\n\n")
        except (ValueError, TypeError):
            lines.append(f"**Confidence**: {confidence}/100\n\n")
    
    # risk score
    risk_score = json_obj.get("risk_score")
    logger.info(f"🔄 [Conversion of research conclusions] risk_score: {risk_score}")
    if risk_score is not None:
        risk_level = "low" if risk_score < 0.3 else "in" if risk_score < 0.7 else "high"
        lines.append(f"**risk score**: {risk_score:.2f} ({risk_level}risk)\n\n")
    
    # Research basis (core content)
    reasoning = json_obj.get("reasoning", "")
    logger.info(f"🔄 [Conversion of research conclusions] reasoning length: {len(reasoning) if reasoning else 0}")
    if reasoning:
        lines.append(f"## 📊 Research basis\n\n{reasoning}\n\n")
    
    # Investment plan summary
    summary = json_obj.get("summary", "")
    logger.info(f"🔄 [Conversion of research conclusions] summary length: {len(summary) if summary else 0}")
    if summary:
        lines.append(f"## 📋 Research summary\n\n{summary}\n\n")
    
    # Risk warning
    risk_warning = json_obj.get("risk_warning", "")
    logger.info(f"🔄 [Conversion of research conclusions] risk_warning length: {len(risk_warning) if risk_warning else 0}")
    if risk_warning:
        lines.append(f"## ⚠️ Risk warning\n\n{risk_warning}\n\n")

    for title, field_name in (
        ("## 🔍 core basis", "core_evidence"),
        ("## ❓ key uncertainties", "uncertainties"),
        ("## 🔄 Determine adjustment conditions", "invalidation_conditions"),
        ("## 👀 Follow-up observations", "watch_items"),
    ):
        items = [item for item in json_obj.get(field_name, []) if item] if isinstance(json_obj.get(field_name, []), list) else []
        if items:
            lines.append(f"{title}\n\n")
            for idx, item in enumerate(items, 1):
                lines.append(f"{idx}. {item}\n")
            lines.append("\n")
    
    result = "\n".join(lines).strip()
    logger.info(f"✅ [Conversion of research conclusions] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _convert_risk_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """Convert risk assessment JSON to Markdown"""
    logger.info(f"🔄 [risk assessment transformation] JSON Field: {list(json_obj.keys())}")
    lines = []

    # risk level
    risk_level = json_obj.get("risk_level", "")
    logger.info(f"🔄 [risk assessment transformation] risk_level: {risk_level}")
    if risk_level:
        level_map = {"low": "🟢", "in": "🟡", "high": "🔴"}
        level_icon = level_map.get(risk_level, "⚪")
        lines.append(f"## ⚠️ risk level\n\n{level_icon} **{risk_level}risk**\n\n")

    # risk score
    risk_score = json_obj.get("risk_score")
    logger.info(f"🔄 [risk assessment transformation] risk_score: {risk_score}")
    if risk_score is not None:
        lines.append(f"**risk score**: {risk_score:.2f}\n\n")

    # Reasons for risk assessment (core content)
    reasoning = json_obj.get("reasoning", "")
    logger.info(f"🔄 [risk assessment transformation] reasoning length: {len(reasoning) if reasoning else 0}")
    if reasoning:
        lines.append(f"## 📊 Risk assessment rationale\n\n{reasoning}\n\n")

    # Main risk points
    key_risks = json_obj.get("key_risks", [])
    logger.info(f"🔄 [risk assessment transformation] key_risks Quantity: {len(key_risks) if isinstance(key_risks, list) else 0}")
    if isinstance(key_risks, list) and key_risks:
        lines.append("## 🔍 Main risk points\n\n")
        for idx, risk in enumerate(key_risks, 1):
            if risk:
                lines.append(f"{idx}. {risk}\n")
        lines.append("\n")

    # Research use boundaries
    risk_control = json_obj.get("risk_control", "")
    logger.info(f"🔄 [risk assessment transformation] risk_control length: {len(risk_control) if risk_control else 0}")
    if risk_control:
        lines.append(f"## 🛡️ Research use boundaries\n\n{risk_control}\n\n")

    # Research Tracking Recommendations Adjustments
    investment_adjustment = json_obj.get("investment_adjustment", "")
    logger.info(f"🔄 [risk assessment transformation] investment_adjustment length: {len(investment_adjustment) if investment_adjustment else 0}")
    if investment_adjustment:
        lines.append(f"## 📈 Research Tracking Advice\n\n{investment_adjustment}\n\n")

    result = "\n".join(lines).strip()
    logger.info(f"✅ [risk assessment transformation] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _convert_final_decision_json_to_markdown(json_obj: Dict[str, Any]) -> str:
    """
    Convert JSON containing final_trade_decision to Markdown

    This function handles the full JSON output by RiskManager, including:
    - Risk Assessment Section (risk_level, risk_score, reasoning, key_risks, risk_control, investment_adjustment) 
    - Final research conclusion part (final_trade_decision nested object)
    """
    logger.info(f"🔄 [Conversion of final research conclusions] JSON Field: {list(json_obj.keys())}")
    lines = []

    # 🔥 Key: Extract final_trade_decision nested object
    final_trade_decision = json_obj.get("final_trade_decision", {})
    logger.info(f"🔄 [Conversion of final research conclusions] final_trade_decision Type: {type(final_trade_decision)}")

    if isinstance(final_trade_decision, dict) and final_trade_decision:
        logger.info(f"🔄 [Conversion of final research conclusions] final_trade_decision Field: {list(final_trade_decision.keys())}")

        # decision summary
        lines.append("# 🎯 Comprehensive research conclusion\n\n")
        lines.append("## current judgment\n\n")

        # research judgment
        action = final_trade_decision.get("analysis_view") or final_trade_decision.get("action", "")
        logger.info(f"🔄 [Conversion of final research conclusions] action: {action}")
        if action:
            action_map = {
                # New compliance terms (optimistic/cautious/neutral) take precedence
                "optimistic": "🟢 optimistic",
                "Prudence": "🟡 Prudence",
                "Neutral": "⚪ Neutral",
                # old market view terminology + Old transaction instructions (compatible with existing data, mapped to new compliance expressions)
                "buy": "🟢 optimistic",
                "hold": "⚪ Neutral",
                "sell": "🟡 Prudence",
                "bullish": "🟢 optimistic",
                "Bearish": "🟡 Prudence",
            }
            action_display = action_map.get(action, action)
            lines.append(f"- **research perspective**: {action_display}\n")

        # Confidence
        confidence = final_trade_decision.get("confidence")
        logger.info(f"🔄 [Conversion of final research conclusions] confidence: {confidence}")
        if confidence is not None:
            # 🔥 Fix: handle both 0-1 decimal and 0-100 integer situations
            try:
                conf_value = float(confidence)
                # If it is a decimal between 0 and 1, convert it to a percentage
                if conf_value <= 1:
                    conf_display = int(conf_value * 100)
                else:
                    conf_display = int(conf_value)
                lines.append(f"- **Confidence**: {conf_display}%\n")
            except (ValueError, TypeError):
                lines.append(f"- **Confidence**: {confidence}%\n")

        lines.append("\n")

        # Research basis (core content)
        reasoning = final_trade_decision.get("reasoning", "")
        logger.info(f"🔄 [Conversion of final research conclusions] reasoning length: {len(reasoning) if reasoning else 0}")
        if reasoning:
            lines.append(f"## 📊 Research basis\n\n{reasoning}\n\n")

        # One sentence summary
        summary = final_trade_decision.get("summary", "")
        logger.info(f"🔄 [Conversion of final research conclusions] summary length: {len(summary) if summary else 0}")
        if summary:
            lines.append(f"## 💡 Research summary\n\n{summary}\n\n")

        # Risk warning
        risk_warning = final_trade_decision.get("risk_warning", "")
        logger.info(f"🔄 [Conversion of final research conclusions] risk_warning length: {len(risk_warning) if risk_warning else 0}")
        if risk_warning:
            lines.append(f"## ⚠️ Risk warning\n\n{risk_warning}\n\n")

        for title, field_name in (
            ("## 🔍 core basis", "core_evidence"),
            ("## ❓ key uncertainties", "uncertainties"),
            ("## 🔄 Determine adjustment conditions", "invalidation_conditions"),
            ("## 👀 Follow-up observations", "watch_items"),
        ):
            items = [item for item in final_trade_decision.get(field_name, []) if item] if isinstance(final_trade_decision.get(field_name, []), list) else []
            if items:
                lines.append(f"{title}\n\n")
                for idx, item in enumerate(items, 1):
                    lines.append(f"{idx}. {item}\n")
                lines.append("\n")
    else:
        logger.warning(f"⚠️ [Conversion of final research conclusions] final_trade_decision Does not exist or is empty, falls back to risk assessment format")
        # If there is no final_trade_decision, fall back to the risk assessment format
        return _convert_risk_json_to_markdown(json_obj)

    result = "\n".join(lines).strip()
    logger.info(f"✅ [Conversion of final research conclusions] Conversion completed, Markdown line number: {len(lines)}, total length: {len(result)}")
    return result


def _extract_investment_debate_reports(debate_state: Any, reports: Dict[str, str]):
    """Extract research team debate reports"""
    # 🔥 Debug log: display the contents of investment_debate_state
    logger.info(f"🔍 [ReportFormatter] investment_debate_state Type: {type(debate_state)}")
    if isinstance(debate_state, dict):
        logger.info(f"🔍 [ReportFormatter] investment_debate_state Field: {list(debate_state.keys())}")

    # multi-investigator
    bull_content = _get_field_value(debate_state, 'bull_history')
    logger.info(f"🔍 [ReportFormatter] bull_history Type: {type(bull_content)}, value: {str(bull_content)[:100] if bull_content else None}")
    if bull_content and isinstance(bull_content, str) and len(bull_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('bull_researcher', bull_content.strip())
        reports['bull_researcher'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: bull_researcher - length: {len(cleaned_content)} (Signature cleared)")

    # short researcher
    bear_content = _get_field_value(debate_state, 'bear_history')
    logger.info(f"🔍 [ReportFormatter] bear_history Type: {type(bear_content)}, value: {str(bear_content)[:100] if bear_content else None}")
    if bear_content and isinstance(bear_content, str) and len(bear_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('bear_researcher', bear_content.strip())
        reports['bear_researcher'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: bear_researcher - length: {len(cleaned_content)} (Signature cleared)")

    # Research Manager Analysis
    decision_content = _get_field_value(debate_state, 'judge_decision')
    logger.info(f"🔍 [ReportFormatter] judge_decision Type: {type(decision_content)}, value: {str(decision_content)[:100] if decision_content else None}")

    # ✅ Fix: only use judge_decision if it has actual content
    # Don't use with empty string str(debate_state) as an alternative
    if decision_content and isinstance(decision_content, str) and len(decision_content.strip()) > 10:
        # 🔥 New: If in JSON format, convert to Markdown
        markdown_content = _clean_report_for_display(
            'research_team_decision',
            _convert_json_to_markdown(decision_content.strip(), "investment"),
        )
        reports['research_team_decision'] = markdown_content
        logger.info(f"📊 [ReportFormatter] Extract: research_team_decision - length: {len(markdown_content)}")
    else:
        logger.warning(f"⚠️ [ReportFormatter] research_team_decision Empty or too short, skip")


def _extract_risk_debate_reports(risk_state: Any, reports: Dict[str, str]):
    """Extract risk management team debate report"""
    # 🔥 Debug log: display the contents of risk_debate_state
    logger.info(f"🔍 [ReportFormatter] risk_debate_state Type: {type(risk_state)}")
    if isinstance(risk_state, dict):
        logger.info(f"🔍 [ReportFormatter] risk_debate_state Field: {list(risk_state.keys())}")

    # activist analyst
    risky_content = _get_field_value(risk_state, 'risky_history')
    logger.info(f"🔍 [ReportFormatter] risky_history: {str(risky_content)[:100] if risky_content else None}")
    if risky_content and isinstance(risky_content, str) and len(risky_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('risky_analyst', risky_content.strip())
        reports['risky_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: risky_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # conservative analyst
    safe_content = _get_field_value(risk_state, 'safe_history')
    logger.info(f"🔍 [ReportFormatter] safe_history: {str(safe_content)[:100] if safe_content else None}")
    if safe_content and isinstance(safe_content, str) and len(safe_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('safe_analyst', safe_content.strip())
        reports['safe_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: safe_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # neutral analyst
    neutral_content = _get_field_value(risk_state, 'neutral_history')
    logger.info(f"🔍 [ReportFormatter] neutral_history: {str(neutral_content)[:100] if neutral_content else None}")
    if neutral_content and isinstance(neutral_content, str) and len(neutral_content.strip()) > 10:
        # 🔥 Clean up signature information generated by AI
        cleaned_content = _clean_report_for_display('neutral_analyst', neutral_content.strip())
        reports['neutral_analyst'] = cleaned_content
        logger.info(f"📊 [ReportFormatter] Extract: neutral_analyst - length: {len(cleaned_content)} (Signature cleared)")

    # risk management decisions
    risk_decision = _get_field_value(risk_state, 'judge_decision')
    logger.info(f"🔍 [ReportFormatter] risk judge_decision Type: {type(risk_decision)}, value: {str(risk_decision)[:100] if risk_decision else None}")

    # ✅ Fix: only use judge_decision if it has actual content
    # Don't use with empty string str(risk_state) as an alternative
    if risk_decision and isinstance(risk_decision, str) and len(risk_decision.strip()) > 10:
        # 🔥 New: If in JSON format, convert to Markdown
        markdown_content = _clean_report_for_display(
            'risk_management_decision',
            _convert_json_to_markdown(risk_decision.strip(), "risk"),
        )
        reports['risk_management_decision'] = markdown_content
        logger.info(f"📊 [ReportFormatter] Extract: risk_management_decision - length: {len(markdown_content)}")
    else:
        logger.warning(f"⚠️ [ReportFormatter] risk_management_decision Empty or too short, skip")


# 🔥 Compliance Modification: Research Conclusion Mapping (English -> Chinese Compliance Terminology)
ACTION_TRANSLATION = {
    'BUY': 'optimistic', 'SELL': 'Prudence', 'HOLD': 'Neutral',
    'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',
    'buy': 'optimistic', 'sell': 'Prudence', 'hold': 'Neutral',  # Compatible with old data
    'bullish': 'optimistic', 'Bearish': 'Prudence', 'Neutral': 'Neutral',  # Compatible with old data
}


def format_decision(
    decision_raw: Dict[str, Any],
    fallback_text: str = "",
    quick_model: str = None,
    stock_code: str = None
) -> Dict[str, Any]:
    """
    Formatting decisions into standard formats

    🔥 Core fix: if decision_raw is missing a key field (reasoning),
    Use SignalProcessor to extract structured information from fallback_text.

    Args:
        decision_raw: original decision dictionary
        fallback_text: Alternate text (usually final_trade_decision or risk_management_decision)
        quick_model: User-selected quick analysis model name
        stock_code: Stock code (used by SignalProcessor to determine currency type)

    Returns:
        Formatted decision dictionary, including action, confidence, risk_score, reasoning
    """
    import re

    if not decision_raw:
        decision_raw = {}

    # 🔥 If decision_raw lacks key fields and has fallback_text, use SignalProcessor to process
    needs_signal_processing = (
        fallback_text and
        len(fallback_text) > 50 and
        (not decision_raw.get('reasoning') and not decision_raw.get('rationale'))
    )

    if needs_signal_processing:
        try:
            from tradingagents.graph.signal_processing import SignalProcessor
            from tradingagents.graph.trading_graph import create_llm_by_provider

            # Find the corresponding configuration from the database according to the incoming quick_model
            quick_llm = None
            target_model = quick_model  # Use user-selected model

            try:
                from pymongo import MongoClient
                from app.core.config import settings

                client = MongoClient(settings.MONGO_URI)
                db = client[settings.MONGO_DB]
                doc = db.system_configs.find_one({"is_active": True}, sort=[("version", -1)])

                if doc and "llm_configs" in doc:
                    selected_cfg = None

                    # 🔥 Prioritize to find the corresponding configuration based on the incoming quick_model
                    if target_model and target_model != "Unknown":
                        for cfg in doc["llm_configs"]:
                            if cfg.get("model_name") == target_model:
                                selected_cfg = cfg
                                logger.info(f"📊 [ReportFormatter] Find user-specified model configuration: {target_model}")
                                break

                    # If the specified model is not found, use the domestic LLM alternative.
                    if not selected_cfg:
                        preferred_providers = ["dashscope", "deepseek", "zhipu", "siliconflow"]
                        for cfg in doc["llm_configs"]:
                            if cfg.get("enabled", True):
                                provider = cfg.get("provider", "").lower()
                                if provider in preferred_providers:
                                    selected_cfg = cfg
                                    logger.info(f"📊 [ReportFormatter] Use alternative domestic models: {cfg.get('model_name')}")
                                    break

                    if selected_cfg:
                        quick_llm = create_llm_by_provider(
                            provider=selected_cfg.get("provider", "dashscope"),
                            model=selected_cfg.get("model_name", "qwen-turbo"),
                            backend_url=selected_cfg.get("default_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
                            temperature=0.1,
                            max_tokens=2000,
                            timeout=60,
                            api_key=selected_cfg.get("api_key")
                        )
                        logger.info(f"📊 [ReportFormatter] Create using model LLM: {selected_cfg.get('model_name')}")
                client.close()
            except Exception as db_err:
                logger.warning(f"⚠️ [ReportFormatter] Failed to get LLM configuration from database: {db_err}")

            # If database configuration fails, use default configuration
            if quick_llm is None:
                quick_llm = create_llm_by_provider(
                    provider="dashscope",
                    model="qwen-turbo",
                    backend_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                    temperature=0.1,
                    max_tokens=2000,
                    timeout=60
                )
                logger.info("📊 [ReportFormatter] Created with default configuration LLM: qwen-turbo")

            signal_processor = SignalProcessor(quick_llm)
            processed = signal_processor.process_signal(fallback_text, stock_code)
            logger.info(f"📊 [ReportFormatter] Use SignalProcessor to process text, the result: action={processed.get('action')}")

            # Merge processing results (preferring the value in decision_raw, if any)
            if not decision_raw.get('reasoning') and processed.get('reasoning'):
                decision_raw['reasoning'] = processed['reasoning']
            if not decision_raw.get('action') and processed.get('action'):
                decision_raw['action'] = processed['action']
            if not decision_raw.get('confidence') and processed.get('confidence'):
                decision_raw['confidence'] = processed['confidence']
            if not decision_raw.get('risk_score') and processed.get('risk_score'):
                decision_raw['risk_score'] = processed['risk_score']

        except Exception as e:
            logger.warning(f"⚠️ [ReportFormatter] SignalProcessor Processing failed: {e}")

    # get action
    action = decision_raw.get('action', 'Neutral')
    chinese_action = ACTION_TRANSLATION.get(action, action) if action else 'Neutral'

    # Get reasoning - clean Markdown format
    # 🔥 Compatible with old and new versions: reasoning or rationale
    # 🔥 Important: reasoning should be extracted from decision_raw, if decision_raw does not have reasoning, use the default value
    # Should not be extracted from fallback_text (usually final_trade_decision) as final_trade_decision will be used to generate summary
    # This is consistent with the way the old engine handles it: in the old engine, if the decision has no reasoning, the default value is used 'No analytical reasoning yet'
    logger.info(f"🔍 [format_decision] ========== Extract reasoning ==========")
    logger.info(f"🔍 [format_decision] decision_raw Type: {type(decision_raw)}")
    if isinstance(decision_raw, dict):
        logger.info(f"🔍 [format_decision] decision_raw Field: {list(decision_raw.keys())}")
        logger.info(f"🔍 [format_decision] decision_raw.get('reasoning'): {decision_raw.get('reasoning', 'None')}")
        logger.info(f"🔍 [format_decision] decision_raw.get('rationale'): {decision_raw.get('rationale', 'None')}")
    
    reasoning = decision_raw.get('reasoning', '') or decision_raw.get('rationale', '')
    logger.info(f"🔍 [format_decision] initial reasoning value: {reasoning[:200] if reasoning else 'None'}")
    
    if reasoning:
        # Clean up the Markdown format in existing reasoning
        reasoning = _clean_markdown(reasoning)
        logger.info(f"🔍 [format_decision] ✅ Extract from decision_raw to reasoning, cleaned length: {len(reasoning)}")
        logger.info(f"🔍 [format_decision] reasoning Cleaned content: {reasoning[:300]}")
    else:
        # 🔥 If there is no reasoning in decision_raw, use the default value (consistent with old engines)
        # Note: should not be extracted from fallback_text to avoid duplication with summary
        reasoning = 'No analytical reasoning yet'
        logger.info(f"🔍 [format_decision] ⚠️ decision_raw There is no reasoning in , use the default value: {reasoning}")
        logger.info(f"🔍 [format_decision] fallback_text length: {len(fallback_text) if fallback_text else 0}")
        if fallback_text:
            logger.info(f"🔍 [format_decision] fallback_text first 200 characters: {fallback_text[:200]}")
            logger.info(f"🔍 [format_decision] ⚠️ Note: reasoning will not be extracted from fallback_text to avoid duplication with summary")

    normalized_lists = normalize_research_brief_lists(
        decision_raw.get('core_evidence'),
        decision_raw.get('uncertainties'),
        decision_raw.get('invalidation_conditions'),
        decision_raw.get('watch_items'),
    )

    return {
        'action': chinese_action,
        'analysis_view': chinese_action,
        'confidence': float(decision_raw.get('confidence', 0.5)),
        'risk_score': float(decision_raw.get('risk_score', 0.3)),
        'reasoning': reasoning or 'No analytical reasoning yet',
        'summary': decision_raw.get('summary', '') or '',
        'risk_warning': decision_raw.get('risk_warning', '') or '',
        'core_evidence': normalized_lists['core_evidence'],
        'uncertainties': normalized_lists['uncertainties'],
        'invalidation_conditions': normalized_lists['invalidation_conditions'],
        'watch_items': normalized_lists['watch_items'],
    }


def _remove_author_signature(text: str) -> str:
    """
    Remove AI-generated signature information (author, date, statement, etc.)
    
    Args:
        text: original text
        
    Returns:
        Cleaned text
    """
    import re
    
    if not text:
        return text
    
    # Remove"Written by:XXX"Format of signature
    text = re.sub(r'Written by[: :]\s*[^\n]+\n?', '', text, flags=re.MULTILINE)
    # Remove"Date:XXX"format date signature
    text = re.sub(r'Date[: :]\s*\d{4}year\d{1,2}month\d{1,2}day\s*\n?', '', text, flags=re.MULTILINE)
    # Remove"Statement:XXX"A statement of format (usually near the signature)
    text = re.sub(r'Statement[: :]\s*[^\n]+this report[^\n]+\n?', '', text, flags=re.MULTILINE)
    # remove contains"Written by", "Date", "Statement"Full signature block (multiple lines)
    text = re.sub(
        r'Written by[: :][^\n]+\n Date[: :][^\n]+\n Statement[: :][^\n]+',
        '',
        text,
        flags=re.MULTILINE | re.DOTALL
    )
    # Remove common signature formats (such as"Written by:XXX·YYY") 
    text = re.sub(r'Written by[: :]\s*[^·\n]+[··][^\n]+\n?', '', text, flags=re.MULTILINE)
    # Remove"analyst·XXX"Format signature (e.g."Bearish Analyst·Li Yan") 
    text = re.sub(r'[^: :\n]+analyst[··][^\n]+\n?', '', text, flags=re.MULTILINE)
    
    # Remove extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


def _clean_markdown(text: str) -> str:
    """
    Clean up Markdown formatting tags

    Args:
        text: original text

    Returns:
        Cleaned text
    """
    import re

    if not text:
        return text

    # 🔥 Process escape characters first (process \\n etc.)
    text = text.replace('\\n', '\n')
    text = text.replace('\\t', ' ')
    text = text.replace('\\r', '')

    # Remove Markdown separators (--- or ___ or ***)
    text = re.sub(r'^[\-_\*]{3,}\s*$', '', text, flags=re.MULTILINE)

    # Remove Markdown title tag (###, ##, #)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    # Remove reference mark (>)
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)

    # Remove bold mark (**text** or __text__)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic mark (*text* or _text_)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    # Remove code block tags (```code```)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)

    # Remove inline tags (`code`)
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove link tag ([text](url))
    text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)

    # Remove list mark (-, *, +, numbers.)
    text = re.sub(r'^[\-\*\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    # Remove Chinese number list markers (one, two, three,)
    text = re.sub(r'^[One, two, three, four, five, six, seven, eight, ninety]+[, \.]\s*', '', text, flags=re.MULTILINE)

    # 🔥 Remove AI-generated signature information
    text = _remove_author_signature(text)

    # Remove extra blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Remove leading whitespace
    text = re.sub(r'^\s+', '', text, flags=re.MULTILINE)

    return text.strip()


def generate_summary_recommendation(
    reports: Dict[str, str],
    decision: Dict[str, Any],
    stock_code: str
) -> Tuple[str, str]:
    """
    Generate summary and recommendation

    🔥 Important: summary and decision.reasoning should have different sources and content
    - summary: Extract analysis summary (first 200 characters) from final_trade_decision or other reports
    - decision.reasoning: Extract reasoning process from final_decision.reasoning (short summary, first 150 characters)
    - recommendation: The unified closing is a research auxiliary prompt and no trading advice is generated.

    Args:
        reports: report dictionary
        decision: Formatted decision making
        stock_code: Stock code

    Returns:
        (summary, recommendation) tuple
    """
    summary = ""
    recommendation = ""

    logger.info(f"🔍 [generate_summary_recommendation] ========== generate summary ==========")
    logger.info(f"🔍 [generate_summary_recommendation] reports fields in: {list(reports.keys())}")
    for report_name in reports.keys():
        if isinstance(reports[report_name], str):
            logger.info(f"🔍 [generate_summary_recommendation] reports['{report_name}'] length: {len(reports[report_name])}, first 100 characters: {reports[report_name][:100]}")

    # 🔥 Important: Consistent with the old engine, summary (analysis summary) is extracted from final_trade_decision first
    # How the old engine handles it: extract summary (first 200 characters) from final_trade_decision in reports first
    # 1. Prefer extracting summary from final_trade_decision (consistent with old engine)
    logger.info(f"🔍 [generate_summary_recommendation] Check 'final_trade_decision' Is it in reports: {'final_trade_decision' in reports}")
    if 'final_trade_decision' in reports:
        content = reports['final_trade_decision']
        logger.info(f"🔍 [generate_summary_recommendation] final_trade_decision content length: {len(content)}")
        logger.info(f"🔍 [generate_summary_recommendation] final_trade_decision first 300 characters: {content[:300]}")
        if len(content) > 50:
            # Clean up Markdown format, extract first 200 characters as summary (consistent with old engine)
            cleaned_content = _clean_markdown(content)
            summary = cleaned_content[:200].strip()
            if len(cleaned_content) > 200:
                summary += "..."
            logger.info(f"🔍 [generate_summary_recommendation] ✅ Extract summary from final_trade_decision: {len(summary)}character")
            logger.info(f"🔍 [generate_summary_recommendation] summary content: {summary[:300]}")

    # 2. Without final_trade_decision, extract summary from other reports
    if not summary:
        logger.info(f"🔍 [generate_summary_recommendation] final_trade_decision Does not exist or is empty, try to extract from other reports")
        for report_name in ['investment_plan', 'trader_investment_plan', 'research_team_decision', 'market_report']:
            logger.info(f"🔍 [generate_summary_recommendation] Check '{report_name}': {'exist' if report_name in reports else 'does not exist'}")
            if report_name in reports:
                content = reports[report_name]
                logger.info(f"🔍 [generate_summary_recommendation] {report_name} content length: {len(content)}")
                if len(content) > 100:
                    cleaned_content = _clean_markdown(content)
                    summary = cleaned_content[:200].strip()
                    if len(cleaned_content) > 200:
                        summary += "..."
                    logger.info(f"🔍 [generate_summary_recommendation] ✅ from {report_name} Extract summary: {len(summary)}character")
                    logger.info(f"🔍 [generate_summary_recommendation] summary content: {summary[:300]}")
                    break

    # 3. Last resort
    if not summary:
        summary = f"Yes{stock_code}The analysis has been completed, please view the detailed report."
        logger.warning(f"⚠️ [Summary] Use alternate summaries")

    # 4. Generate recommendations (unified research auxiliary tips)
    logger.info(f"🔍 [generate_summary_recommendation] ========== generate recommendation ==========")
    logger.info(f"🔍 [generate_summary_recommendation] decision Field: {list(decision.keys())}")
    # 🔥 recommendation Should be based on the decision's action, target_price, and a short summary of the reasoning
    # Note: Complete reasoning is not used here to avoid confusion with"Research basis"Repeat
    action = decision.get('action') or decision.get('analysis_view') or 'Neutral'
    reasoning = decision.get('reasoning', '')
    
    logger.info(f"🔍 [generate_summary_recommendation] decision.action: {action}")
    logger.info(f"🔍 [generate_summary_recommendation] decision.reasoning length: {len(reasoning)}, content: {reasoning[:200]}")

    recommendation = f"Research perspective:{action}. Please use detailed reporting to focus on changes in evidence, risk factors and subsequent disclosures."
    if reasoning:
        short_reasoning = reasoning[:60] + "..." if len(reasoning) > 60 else reasoning
        recommendation += f" Core basis:{short_reasoning}"

    if not recommendation:
        recommendation = "Please refer to the detailed research report, focusing on fundamental changes, market environment and risk factors."
        logger.warning(f"⚠️ [Recommendation] Use backup research tips")
    
    logger.info(f"🔍 [generate_summary_recommendation] recommendation final content: {recommendation[:300]}")

    logger.info(f"✅ [Summary/Recommendation] summary={len(summary)}character, recommendation={len(recommendation)}character")
    return summary, recommendation


def calculate_risk_level(risk_score: float) -> str:
    """
    Calculate risk level based on risk score

    Args:
        risk_score: risk score (0-1)

    Returns:
        Risk level string
    """
    if risk_score >= 0.7:
        return "high"
    elif risk_score >= 0.4:
        return "medium"
    else:
        return "low"


def format_analysis_result(
    raw_result: Dict[str, Any],
    stock_code: str,
    stock_name: str,
    analysis_date: str,
    task_id: str,
    analysts: list = None,
    research_depth: str = "Standard",
    quick_model: str = "Unknown",
    deep_model: str = "Unknown",
    execution_time: float = 0,
) -> Dict[str, Any]:
    """
    Unified analysis result formatting function

    Args:
        raw_result: Raw analysis results (usually LangGraph state)
        stock_code: Stock code
        stock_name: Stock name
        analysis_date: Analysis date
        task_id: Task ID
        analysts: List of selected analysts
        research_depth: Research depth
        quick_model: Quickly analyze models
        deep_model: Deep analysis model
        execution_time: Execution time (seconds)

    Returns:
        Complete analysis results after formatting
    """
    # 1. Extract report from raw_result
    logger.info(f"🔍 [ReportFormatter] ========== Start formatting analysis results ==========")
    logger.info(f"🔍 [ReportFormatter] stock_code={stock_code}, stock_name={stock_name}")
    
    reports = extract_reports_from_state(raw_result)
    logger.info(f"🔍 [ReportFormatter] Extract to {len(reports)} reports: {list(reports.keys())}")
    for report_name, report_content in reports.items():
        if isinstance(report_content, str):
            logger.info(f"🔍 [ReportFormatter] reports['{report_name}'] length: {len(report_content)}, first 100 characters: {report_content[:100]}")

    # 2. Parse and format decisions
    # 🔥 v2.0 Special handling of the engine:
    # - final_decision: May not exist or be empty
    # - action_advice: ActionAdvisorV2 The output of contains research observations and reasoning
    # - final_trade_decision: RiskManagerV2 The output of , containing the full risk assessment report (should not be used for reasoning)
    final_decision = raw_result.get("final_decision", {})
    action_advice = raw_result.get("action_advice", "")
    final_trade_decision = raw_result.get("final_trade_decision", "")

    # 🔥 Detailed log: check the contents of each field
    logger.info(f"🔍 [ReportFormatter] ========== Check raw data fields ==========")
    logger.info(f"🔍 [ReportFormatter] final_decision Type: {type(final_decision)}")
    if isinstance(final_decision, dict):
        logger.info(f"🔍 [ReportFormatter] final_decision Field: {list(final_decision.keys())}")
        logger.info(f"🔍 [ReportFormatter] final_decision.target_price: {final_decision.get('target_price')}")
        logger.info(f"🔍 [ReportFormatter] final_decision.reasoning: {str(final_decision.get('reasoning', ''))[:200] if final_decision.get('reasoning') else 'None'}")
    else:
        logger.info(f"🔍 [ReportFormatter] final_decision value: {str(final_decision)[:200]}")
    
    # 🔥 Check action_advice (research observation for v2.0 engine)
    logger.info(f"🔍 [ReportFormatter] action_advice Type: {type(action_advice)}")
    if action_advice:
        if isinstance(action_advice, dict):
            action_advice_content = action_advice.get("content", str(action_advice))
            logger.info(f"🔍 [ReportFormatter] action_advice is a dictionary, field: {list(action_advice.keys())}")
        else:
            action_advice_content = str(action_advice)
        logger.info(f"🔍 [ReportFormatter] action_advice existence, length: {len(action_advice_content)}")
        logger.info(f"🔍 [ReportFormatter] action_advice first 300 characters: {action_advice_content[:300]}")
    else:
        logger.info(f"🔍 [ReportFormatter] action_advice Does not exist or is empty")
    
    logger.info(f"🔍 [ReportFormatter] final_trade_decision Type: {type(final_trade_decision)}")
    logger.info(f"🔍 [ReportFormatter] final_trade_decision length: {len(final_trade_decision) if final_trade_decision else 0}")
    if final_trade_decision:
        final_trade_decision_str = str(final_trade_decision)
        logger.info(f"🔍 [ReportFormatter] final_trade_decision first 300 characters: {final_trade_decision_str[:300]}")
        logger.info(f"🔍 [ReportFormatter] final_trade_decision Is it in reports: {'final_trade_decision' in reports}")
        if 'final_trade_decision' in reports:
            logger.info(f"🔍 [ReportFormatter] reports['final_trade_decision'] length: {len(reports['final_trade_decision'])}, first 300 characters: {reports['final_trade_decision'][:300]}")

    # 🔥 v2.0 Special processing of the engine: priority is extracted from action_advice reasoning
    # If final_decision has no reasoning and action_advice exists, try to extract it from action_advice
    if isinstance(final_decision, dict) and not final_decision.get('reasoning'):
        if action_advice:
            # Try to extract from action_advice reasoning
            if isinstance(action_advice, dict):
                action_advice_content = action_advice.get("content", str(action_advice))
            else:
                action_advice_content = str(action_advice)
            
            # Try to parse JSON format action_advice
            import json
            try:
                if isinstance(action_advice_content, str) and ("{" in action_advice_content or "```json" in action_advice_content):
                    # Extract JSON part
                    json_str = action_advice_content
                    if "```json" in json_str:
                        json_start = json_str.find("```json") + 7
                        json_end = json_str.find("```", json_start)
                        if json_end > json_start:
                            json_str = json_str[json_start:json_end].strip()
                    
                    if json_str.strip().startswith("{"):
                        action_advice_json = json.loads(json_str)
                        # Extract from JSON reasoning
                        if isinstance(action_advice_json, dict):
                            reasoning_from_advice = action_advice_json.get("reasoning") or action_advice_json.get("detailed_analysis", "")
                            if reasoning_from_advice:
                                final_decision['reasoning'] = reasoning_from_advice
                                logger.info(f"✅ [ReportFormatter] Extracted from action_advice reasoning: {len(reasoning_from_advice)}character")
            except Exception as e:
                logger.warning(f"⚠️ [ReportFormatter] Parsing action_advice JSON failed: {e}")

    # 🔥 Pass in quick_model and stock_code to use the model selected by the user
    # 🔥 Important: For the v2.0 engine, if final_decision has no reasoning, try to extract it from action_advice
    # If action_advice is not available, format_decision will use the default value 'No analytical reasoning yet' (consistent with the old engine)
    # final_trade_decision should not be used as a fallback for reasoning because final_trade_decision will be used to generate summary
    fallback_for_reasoning = ""
    if action_advice:
        # Prefer using action_advice as a fallback for reasoning (try to extract reasoning from action_advice)
        if isinstance(action_advice, dict):
            fallback_for_reasoning = action_advice.get("content", str(action_advice))
        else:
            fallback_for_reasoning = str(action_advice)
    
    formatted_decision = format_decision(
        final_decision,
        fallback_for_reasoning,  # Use action_advice if present, otherwise format_decision will use the default value
        quick_model=quick_model,
        stock_code=stock_code
    )
    logger.info(f"🔍 [ReportFormatter] formatted_decision: action={formatted_decision.get('action')}, target_price={formatted_decision.get('target_price')}, reasoning length={len(formatted_decision.get('reasoning', ''))}")

    # 3. Generate summary and recommendation
    # 🔥 Important: summary should be extracted from investment_plan or other comprehensive reports, not from final_trade_decision
    # final_trade_decision is a risk assessment report and should not be used as summary
    summary, recommendation = generate_summary_recommendation(
        reports, formatted_decision, stock_code
    )

    # 4. Calculate risk level
    risk_level = calculate_risk_level(formatted_decision.get('risk_score', 0.3))

    # 5. Build the complete result
    result = {
        "success": True,
        "analysis_id": str(uuid.uuid4()),
        "task_id": task_id,
        "stock_code": stock_code,
        "stock_symbol": stock_code,
        "stock_name": stock_name,
        "analysis_date": analysis_date,

        # Core fields - the front end depends on these
        "summary": summary,
        "recommendation": recommendation,
        "confidence_score": formatted_decision.get("confidence", 0.5),
        "risk_level": risk_level,
        "key_points": [],

        # decision Field - the front end displays research tendencies, research basis, etc.
        "decision": formatted_decision,

        # Report content - including long, short, aggressive, conservative, neutral, etc.
        "reports": reports,

        # Original state (for debugging)
        "state": raw_result,
        "detailed_analysis": final_decision,

        # Analyst and model information
        "analysts": analysts or [],
        "research_depth": research_depth,
        "model_info": f"{quick_model}/{deep_model}",
        "quick_model": quick_model,
        "deep_model": deep_model,

        # Performance indicators
        "execution_time": execution_time,
        "tokens_used": raw_result.get("tokens_used", 0),
        "performance_metrics": raw_result.get("performance_metrics", {}),
    }

    # 🔥 final result log
    logger.info(f"🔍 [ReportFormatter] ========== Final formatting result ==========")
    logger.info(f"🔍 [ReportFormatter] result.decision.reasoning length: {len(formatted_decision.get('reasoning', ''))}, content: {formatted_decision.get('reasoning', '')[:300]}")
    logger.info(f"🔍 [ReportFormatter] result.summary length: {len(summary)}, content: {summary[:300]}")
    logger.info(f"🔍 [ReportFormatter] result.recommendation length: {len(recommendation)}, content: {recommendation[:300]}")
    logger.info(f"🔍 [ReportFormatter] ========== Formatting completed ==========")
    logger.info(f"✅ [ReportFormatter] Formatting completed: decision.action={formatted_decision.get('action')}, reports={len(reports)}a")
    return result
