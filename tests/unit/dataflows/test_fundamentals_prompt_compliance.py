import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_fundamentals_analyst_v2_templates_are_research_mode() -> None:
    templates_path = ROOT / "exports" / "current_db_templates.json"
    templates = json.loads(templates_path.read_text(encoding="utf-8"))

    target_templates = [
        item for item in templates
        if item.get("agent_name") == "fundamentals_analyst_v2"
        and item.get("template_name") in {
            "Fundamental Analyst v2.0 - Aggressive",
            "Fundamental Analyst v2.0 - Neutral",
            "Fundamental Analyst v2.0 - Conservative",
        }
    ]

    assert len(target_templates) == 3

    required_phrases = [
        "core observation",
        "Financial and operating signals",
        "Valuation background",
        "valuation premium",
        "Summary",
        "get_financial_statements",
        "get_cash_flow_statement",
        "get_peer_comparison",
        "Tool results not provided",
        "Cumulative caliber during the reporting period",
        "Single quarter derivation",
        "Industry characteristics",
        "Not applicable",
        "Historical financials, historical valuation ranges and disclosed operating data",
        "Current stock price, rise and fall, trading volume, current total market capitalization",
        "snapshot date",
        "must not be written as As of analysis date Or replace the valuation date with the analysis date",
        "You can t just change the date without explaining the reason",
        "core observation` Article 1 or `## Valuation background` Beginning",
        "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day.",
        "Do not end the report directly",
    ]

    for template in target_templates:
        content = template["content"]
        combined_text = "\n".join(str(content.get(field, "")) for field in content)
        output_format = str(content.get("output_format", ""))
        user_prompt = str(content.get("user_prompt", ""))
        analysis_requirements = str(content.get("analysis_requirements", ""))

        assert "price analysis range" not in output_format
        assert "Reasonable price range" not in output_format
        assert "Room for upside" not in output_format
        assert "Downside" not in output_format
        assert "Position recommendations" not in output_format
        assert "Risk exposure recommendations" not in output_format
        assert "Suggestions" not in output_format

        assert "No trading advice may be output" in user_prompt
        assert "target price" in user_prompt
        assert "Do not use LLM s own knowledge to supplement data" in user_prompt
        assert "The current stock price and current total market capitalization are not allowed to be included in the company profile, core observations or summary." in user_prompt
        assert "You must also indicate the snapshot date corresponding to the indicator." in user_prompt
        assert "must not be written as As of analysis date Or replace the valuation date with the analysis date" in user_prompt
        assert "You can t just change the date without explaining the reason" in user_prompt
        assert "core observation` Article 1 or `## Valuation background` Beginning" in user_prompt
        assert "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day." in user_prompt
        assert "You can write:" in user_prompt
        assert "Do not write:" in user_prompt
        assert "No need to list separately Questions to be verified " in user_prompt
        assert "Does not require mechanical coverage of all common financial indicators" in user_prompt
        assert "The results of get_stock_fundamentals_unified, get_financial_statements and get_cash_flow_statement must be obtained before generating the text." in user_prompt
        assert "Q2/Q3/Q4 Not a single quarter value" in combined_text
        assert (
            "Prioritize using these fields to analyze quarterly changes" in combined_text
            or "Prefer using this field to describe quarterly changes" in combined_text
        )
        assert "margin of safety" in user_prompt
        assert "Economic turning point" in user_prompt
        assert "No output allowed" in analysis_requirements
        assert "trading action" in analysis_requirements
        assert "Examples of expressions" in analysis_requirements
        assert "No need to list separately Questions to be verified " in analysis_requirements
        assert "Do not write its absence directly as a risk or data gap" in analysis_requirements
        assert "Must first obtain overall fundamentals, most recent quarter financial report details and most recent quarterly cash flow statement" in analysis_requirements
        assert "Also do not write these fields into `## Company Profile`, `## core observation`, `## Valuation background` or `## Summary`" in analysis_requirements
        assert "You must also indicate the snapshot date corresponding to the indicator." in analysis_requirements
        assert "must not be written as As of analysis date Or replace the valuation date with the analysis date" in analysis_requirements
        assert "You can t just change the date without explaining the reason" in analysis_requirements
        assert "core observation` Article 1 or `## Valuation background` Beginning" in analysis_requirements
        assert "There is currently no stable post-closing daily frequency data corresponding to the analysis day, so the historical valuation quantiles and peer valuations are analyzed based on the previous available trading day." in analysis_requirements
        assert (
            "Do not add Q1-Q4 directly" in analysis_requirements
            or "Or add Q1-Q4 directly" in analysis_requirements
        )
        assert "Single quarter derivation" in combined_text
        assert "margin of safety" in analysis_requirements
        assert "Economic turning point" in analysis_requirements
        assert "Do not add any attribution information to the report" in combined_text
        assert "Prohibiting any false names, authorships or attributions" in combined_text

        for phrase in required_phrases:
            assert phrase in combined_text


def test_fundamentals_analyst_v2_default_tools_include_peer_comparison() -> None:
    adapter_source = (ROOT / "core" / "agents" / "adapters" / "fundamentals_analyst_v2.py").read_text(encoding="utf-8")
    config_source = (ROOT / "core" / "agents" / "config.py").read_text(encoding="utf-8")

    assert "default_tools=[\"get_stock_fundamentals_unified\", \"get_financial_statements\", \"get_cash_flow_statement\", \"get_peer_comparison\"]" in adapter_source
    assert "max_tool_calls=4" in adapter_source
    # config.py A more conservative default tool list is retained in the file, and the metadata in the adapter file shall prevail when running.
    assert "fundamentals_analyst_v2" in config_source