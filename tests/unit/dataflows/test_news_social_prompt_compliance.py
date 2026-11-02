import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_module(relative_path: str, module_name: str):
    module_path = ROOT / relative_path
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def _load_templates(relative_path: str):
    payload = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get("data", {}).get("prompt_templates", [])


def test_legacy_news_analyst_migration_keeps_inline_validation_note_only() -> None:
    module = _load_module(
        "scripts/compliance/migrate_prompt_templates_to_research_mode.py",
        "migrate_prompt_templates_to_research_mode_legacy_news",
    )

    legacy_output_format = module.transform_text("original", "news_analyst", "output_format", "news_analyst")
    legacy_user_prompt = module.transform_text("original", "news_analyst", "user_prompt", "news_analyst")
    legacy_system_prompt = module.transform_text("original", "news_analyst", "system_prompt", "news_analyst")
    v2_output_format = module.transform_text("original", "news_analyst", "output_format", "news_analyst_v2")

    assert "4. Issues to be verified" not in legacy_output_format
    assert "No need to start a new chapter" in legacy_output_format
    assert "4. Questions to be further verified" not in legacy_user_prompt
    assert "No need to start a new chapter" in legacy_user_prompt
    assert "Only research observations, evidence descriptions and impact assessments are output" in legacy_system_prompt
    assert "Risk warnings and issues to be verified" not in legacy_system_prompt
    assert "4. Issues to be verified" in v2_output_format


def test_legacy_news_analyst_export_template_uses_three_section_format() -> None:
    templates = _load_templates("exports/current_db_templates.json")

    target_templates = [
        item
        for item in templates
        if item.get("agent_name") == "news_analyst"
        and item.get("template_name") == "System Neutral Template"
    ]

    assert len(target_templates) == 1

    content = target_templates[0]["content"]
    system_prompt = str(content.get("system_prompt", ""))
    analysis_requirements = str(content.get("analysis_requirements", ""))
    output_format = str(content.get("output_format", ""))

    assert "4. Issues to be verified" not in output_format
    assert output_format.startswith("Use Markdown to output: 1. Core observations; 2. Key evidence; 3. Impact assessment.")
    assert "No need to start a new chapter" in output_format
    assert "Only research observations, evidence descriptions and impact assessments are output" in system_prompt
    assert "Risk warnings and issues to be verified" not in system_prompt
    assert "The source of evidence and the impact of the conclusion must be given simultaneously" in analysis_requirements
    assert "No need to start a new chapter" in analysis_requirements


@pytest.mark.parametrize(
    "relative_path",
    [
        "exports/current_db_templates.json",
        "install/database_export_config_2026-02-10.json",
    ],
)
def test_news_analyst_v2_templates_follow_legacy_structure_with_compliance(relative_path: str) -> None:
    templates = _load_templates(relative_path)

    target_templates = [
        item
        for item in templates
        if item.get("agent_name") == "news_analyst_v2"
        and item.get("template_name")
        in {
            "News Analyst v2.0 - Aggressive",
            "News Analyst v2.0 - Neutral",
            "News Analyst v2.0 - Conservative",
        }
    ]

    assert len(target_templates) == 3

    required_phrases = [
        "Latest news summary",
        "News impact analysis",
        "Market Sentiment Assessment",
        "analysis point of view",
        "short term response expectations",
        "Impact on overall research conclusions",
        "News evaluation",
        "Impact on overall research conclusions",
        "get_stock_news_unified",
        "Multiple headlines essentially describing the same event",
        "If the tool only returns the title",
        "Tool results not provided",
        "Positive side",
        "Cautious",
        "major benefits",
        "Short-term market reaction expectations",
        "No less than 700 words",
    ]

    output_format_forbidden_phrases = [
        "target price",
        "price range",
        "support level",
        "resistance level",
        "position",
    ]

    for template in target_templates:
        content = template["content"]
        combined_text = "\n".join(str(content.get(field, "")) for field in content)
        analysis_requirements = str(content.get("analysis_requirements", ""))
        user_prompt = str(content.get("user_prompt", ""))
        output_format = str(content.get("output_format", ""))
        constraints = str(content.get("constraints", ""))

        for phrase in required_phrases:
            assert phrase in combined_text

        for phrase in output_format_forbidden_phrases:
            assert phrase not in output_format

        assert "objective and neutral" in user_prompt
        assert "Summary of latest news events" in user_prompt
        assert "Assessment of changes in market sentiment" in user_prompt
        assert "Short-term market reaction expectations" in user_prompt
        assert "Tool results not provided" in user_prompt
        assert "Do not make up details" in user_prompt
        assert "Do not output investment recommendations, target prices, price ranges, position plans, or any execution instructions" in user_prompt
        assert "News classification analysis" in analysis_requirements
        assert "impact assessment" in analysis_requirements
        assert "analysis point of view" in analysis_requirements
        assert "No need for separate chapters" in analysis_requirements
        assert "Impact on overall research conclusions" in analysis_requirements
        assert "Short-term market reaction expectations (1-3 days)" in analysis_requirements
        assert "News analysis report" in output_format
        assert "Market Sentiment Assessment" in output_format
        assert "analysis point of view" in output_format
        assert "Questions to be verified" not in output_format
        assert "Do not add any attribution information to the report" in constraints


@pytest.mark.parametrize(
    "relative_path",
    [
        "exports/current_db_templates.json",
        "install/database_export_config_2026-02-10.json",
    ],
)
def test_social_analyst_v2_templates_follow_legacy_structure_with_compliance(relative_path: str) -> None:
    templates = _load_templates(relative_path)

    target_templates = [
        item
        for item in templates
        if item.get("agent_name") == "social_analyst_v2"
        and item.get("template_name")
        in {
            "Social Analyst v2.0 - Aggressive",
            "Social Analyst v2.0 - Neutral",
            "Social Analyst v2.0 - Conservative",
        }
    ]

    assert len(target_templates) == 3

    required_phrases = [
        "Emotional direction and heat",
        "Opinion structure and channel differences",
        "Emotional changes and differentiation",
        "Noise and risk",
        "Impact on overall research conclusions",
        "Follow-up observations",
        "get_stock_sentiment_unified",
        "If the tool explicitly states that the current results are from news fallback sentiment summaries",
        "Do not analyze this dimension",
        "Tool results not provided",
        "Positive side",
        "Cautious",
        "The emotional turning point has arrived",
        "Bullish across the board",
        "No less than 700 words",
    ]

    output_format_forbidden_phrases = [
        "target price",
        "price range",
        "support level",
        "resistance level",
        "position",
    ]

    for template in target_templates:
        content = template["content"]
        combined_text = "\n".join(str(content.get(field, "")) for field in content)
        analysis_requirements = str(content.get("analysis_requirements", ""))
        user_prompt = str(content.get("user_prompt", ""))
        output_format = str(content.get("output_format", ""))
        constraints = str(content.get("constraints", ""))

        for phrase in required_phrases:
            assert phrase in combined_text

        for phrase in output_format_forbidden_phrases:
            assert phrase not in output_format

        assert "objective and neutral" in user_prompt
        assert "This dimension is not analyzed yet" in user_prompt
        assert "News Fallback Sentiment Summary" in user_prompt
        assert "Continue to heat up" in user_prompt
        assert "Do not output investment recommendations, target prices, price ranges, position plans, or any execution instructions" in user_prompt
        assert "Opinion structure and channel differences" in analysis_requirements
        assert "Emotional changes and differentiation" in analysis_requirements
        assert "Impact on overall research conclusions" in analysis_requirements
        assert "Do not add any attribution information to the report" in constraints
