import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_templates(relative_path: str):
    payload = json.loads((ROOT / relative_path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    return payload.get("data", {}).get("prompt_templates", [])


@pytest.mark.parametrize(
    "relative_path",
    [
        "exports/current_db_templates.json",
        "install/database_export_config_2026-02-10.json",
    ],
)
def test_market_analyst_v2_templates_are_research_observation_mode(relative_path: str) -> None:
    templates = _load_templates(relative_path)

    target_templates = [
        item for item in templates
        if item.get("agent_name") == "market_analyst_v2"
        and item.get("template_name") in {
            "Market Analyst v2.0 - Aggressive",
            "Market Analyst v2.0 - Neutral",
            "Market Analyst v2.0 - Conservative",
        }
    ]

    assert len(target_templates) == 3

    required_phrases = [
        "Basic stock information",
        "Technical indicator analysis",
        "Moving Average (MA) Analysis",
        "MACD Indicator analysis",
        "RSI relative strength indicator",
        "Bollinger Bands (BOLL) analysis",
        "Price trend analysis",
        "Short term trend (5-10 trading days)",
        "Medium-term trend (20-60 trading days)",
        "Volume analysis",
        "comprehensive assessment",
        "Impact on overall research conclusions",
        "Follow-up observation points",
        "get_stock_market_data_unified",
        "actual data date",
        "Conflict of short-term and medium-term signals",
        "Only the real prices, technical indicators and transaction data returned by the tool can be used",
        "Can reference the actual value returned by the tool",
        "Examples of expressions",
        "If the tool results only provide current values, statistics for the last 5 days or a single snapshot",
        "Moving average arrangement relationship",
        "Moving average slope direction",
        "Only indicate whether these signals strengthen, weaken or neutralize the overall research and why.",
        "Subsequent text must be consistent with the table and values",
        "Do not write follow-up observation points as Is it standing firmly above MA5? ",
        "cannot be written as MA60 higher than MA20 ",
        "don t write No effective breakthrough has been formed ",
        "don t write Not yet firmly above MA5 ",
        "Does the histogram appear to be continuously enlarged?",
        "There is some room for upside",
        "A word-by-word self-check must be done before output",
        "Not allowed to appear stand on  stand firm ",
    ]

    output_format_forbidden_phrases = [
        "target price",
        "price range",
        "support level",
        "resistance level",
        "key price",
        "breakout call price",
        "Below the put price",
        "Risk-benefit ratio",
        "Position ratio",
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

        assert "No trading advice may be output" in user_prompt
        assert "support resistance level" in user_prompt
        assert "Breakout and breakout conditions" in user_prompt
        assert "Do not use LLM s own knowledge to supplement data" in user_prompt
        assert "Do not write numbers as target prices, support and resistance levels, key execution levels, trigger thresholds or trading plans" in user_prompt
        assert "If short-term and medium-term signals conflict" in user_prompt
        assert "actual data date" in user_prompt
        assert "You can write:" in user_prompt
        assert "Do not write:" in user_prompt
        assert "Basic stock information" in analysis_requirements
        assert "Technical indicator analysis" in analysis_requirements
        assert "Moving Average (MA) Analysis" in analysis_requirements
        assert "MACD Indicator analysis" in analysis_requirements
        assert "RSI relative strength indicator" in analysis_requirements
        assert "Bollinger Bands (BOLL) analysis" in analysis_requirements
        assert "Price trend analysis" in analysis_requirements
        assert "comprehensive assessment" in analysis_requirements
        assert "Current price, change and volume" in analysis_requirements
        assert "Normally no less than 800 words" in combined_text
        assert "Follow-up observation points" in analysis_requirements
        assert "If short-term and medium-term signals conflict" in analysis_requirements
        assert "actual data date" in analysis_requirements
        assert "Examples of expressions" in analysis_requirements
        assert "Tool results not provided" in combined_text
        assert "Judgments can only be made based on the real prices, technical indicators and transaction data returned by the tool." in combined_text
        assert "Allow quoting real values to illustrate facts" in combined_text
        assert "The histogram continues to zoom in" in combined_text
        assert "Investment ratings must not be exported" in analysis_requirements
        assert "Target price must not be output" in analysis_requirements
        assert "Buy and sell are not allowed to be output" in analysis_requirements
        assert "Breaking through 32.5 yuan will confirm the main rise." in combined_text
        assert "The support level is 28 yuan, if it falls below, stop loss" in combined_text
        assert "price analysis range" in combined_text
        assert "Do not add any attribution information to the report" in constraints
        assert "Prohibiting any false names, authorships or attributions" in constraints