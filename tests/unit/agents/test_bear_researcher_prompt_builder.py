import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_module(relative_path: str, module_name: str):
    module_path = ROOT / relative_path
    module_spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert module_spec is not None and module_spec.loader is not None
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def test_bear_researcher_builder_restores_debate_context_and_source_constraints() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts_bear",
    )

    content = module.build_bear_researcher_content("neutral")

    assert "Current Analytical Markets:{market_name}" in content["system_prompt"]
    assert "Please use company name first {company_name} " in content["system_prompt"]
    assert "Risks and Challenges" in content["analysis_requirements"]
    assert "competitive disadvantage" in content["analysis_requirements"]
    assert "negative indicators" in content["analysis_requirements"]
    assert "Optimistic argument" in content["analysis_requirements"]
    assert "Lessons learned" in content["analysis_requirements"]
    assert "During multiple rounds of debate" in content["analysis_requirements"]
    assert "There is currently no new high-quality risk evidence in this round" in content["analysis_requirements"]
    assert "There are no new observation signals in this round." in content["analysis_requirements"]
    assert "Social Media Sentiment Report" in content["user_prompt"]
    assert "The latest optimistic argument" in content["user_prompt"]
    assert "Reflections and Lessons Learned" in content["user_prompt"]
    assert "There are no new observation signals in this round, so this title can be omitted" in content["output_format"]
    assert "Each key argument must be marked with [ ] at the end of the sentence as the source." in content["output_format"]
    assert " [Fundamental report]" in content["analysis_requirements"]
    assert "LLM inside knowledge" in content["constraints"]
    assert "This data is not provided in the report" in content["constraints"]
    assert "Unable to determine based on existing reports" in content["constraints"]
    assert "2023 year" in content["constraints"]
    assert "last year" in content["constraints"]


def test_bear_researcher_aggressive_bias_points_to_downside_not_upside() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts_bear_aggressive",
    )

    content = module.build_bear_researcher_content("aggressive")

    assert "Downward catalyst" in content["system_prompt"]
    assert "Upward catalyst" not in content["system_prompt"]


def test_bear_researcher_fallback_prompt_uses_consistent_placeholders() -> None:
    source = (ROOT / "core/agents/adapters/bear_researcher_v2.py").read_text(encoding="utf-8")

    assert "Market research report:{reports.get('market_report', '')}" in source
    assert "Market research report:{reports.get('market_research_report', '')}" not in source
    assert "Each key argument must be marked with [ ] at the end of the sentence as the source." in source
    assert "The latest optimistic argument" in source
    assert "There is currently no new high-quality risk evidence or premise modifications" in source
    assert "There are no new observation signals in this round, so this title can be omitted" in source


def test_bull_researcher_builder_and_fallback_allow_incremental_rounds() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts_bull",
    )

    content = module.build_bull_researcher_content("neutral")
    source = (ROOT / "core/agents/adapters/bull_researcher_v2.py").read_text(encoding="utf-8")

    assert "During multiple rounds of debate" in content["analysis_requirements"]
    assert "There is no new high-quality supporting evidence in this round." in content["analysis_requirements"]
    assert "There are no new observation signals in this round." in content["analysis_requirements"]
    assert "There are no new observation signals in this round, so this title can be omitted" in content["output_format"]
    assert "Market research report:{reports.get('market_report', '')}" in source
    assert "Market research report:{reports.get('market_research_report', '')}" not in source
    assert "There is currently no new high-quality supporting evidence or premise modifications." in source
    assert "There are no new observation signals in this round, so this title can be omitted" in source


def test_research_manager_builder_restores_strongest_case_structure_without_trading_fields() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts_manager",
    )

    content = module.build_research_manager_content("neutral")

    assert "The strongest founding logic of both parties" in content["system_prompt"]
    assert "First, review the strongest arguments of both parties with equal weight." in content["system_prompt"]
    assert "The 2-3 strongest logics of bullishness and bearishness" in content["analysis_requirements"]
    assert "consensus point" in content["analysis_requirements"]
    assert "sources of disagreement" in content["analysis_requirements"]
    assert "Have market pricing reflected expectations?" in content["analysis_requirements"]
    assert "The strongest basis from multiple parties -> The strongest basis for the short side -> consensus point -> sources of disagreement -> final judgment" in content["analysis_requirements"]
    assert "The strongest basis for bulls, the strongest basis for bears, consensus between both parties, and the root of key differences" in content["output_format"]
    assert "price_analysis_range" not in content["output_format"]
    assert "risk_exposure_ratio" not in content["output_format"]
    assert "investment opportunities" not in content["user_prompt"]


def test_research_manager_fallback_tracks_structured_reasoning_without_old_trading_language() -> None:
    source = (ROOT / "core/agents/adapters/research_manager_v2.py").read_text(encoding="utf-8")

    assert "Don t write either side off as a straw man" in source
    assert "The differences mainly come from data interpretation, premise assumptions, time dimension or the degree of market pricing reflection." in source
    assert "Has the market already priced in some optimistic/pessimistic expectations?" in source
    assert "The strongest basis for the optimistic scenario, the strongest basis for the cautious scenario, consensus between both parties, and key sources of disagreement" in source
    assert "investment opportunities" not in source


def test_trader_builder_and_fallback_prioritize_manager_judgment_without_trading_regression() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts_trader",
    )

    content = module.build_trader_content("neutral")
    source = (ROOT / "core/agents/adapters/trader_v2.py").read_text(encoding="utf-8")

    assert "The conclusion in one sentence should be explained as if it were explained to a friend" in content["system_prompt"]
    assert "Don t retell all reports equally into a running account" in content["system_prompt"]
    assert "Don t write directly Valuation repair logic  provide defense  Material not provided  Risk review conclusions not provided  Investment decision-making materials not provided " in content["system_prompt"]
    assert "The total length of the entire user version of the research briefing is controlled between 500-800 Chinese characters." in content["analysis_requirements"]
    assert "don t put low PB Just put a conclusion in one sentence" in content["analysis_requirements"]
    assert "500-800 Chinese characters" in content["analysis_requirements"]
    assert "complete vernacular passage" in content["output_format"]
    assert "Historical transaction records can only be used as background reference" in content["analysis_requirements"]
    assert "The user version of the briefing should be explained as if it were to ordinary people" in content["user_prompt"]
    assert "It cannot be written in just a few short sentences" in content["user_prompt"]
    assert "Historical transaction records can only be used as background" in content["user_prompt"]
    assert "One sentence conclusion" in source
    assert "Historical transaction records" in source
    assert "research brief" in source
    assert "Does not constitute investment advice" in source


def test_trader_runtime_keeps_sentiment_report_and_structured_plan_rendering() -> None:
    trader_source = (ROOT / "core/agents/trader.py").read_text(encoding="utf-8")
    adapter_source = (ROOT / "core/agents/adapters/trader_v2.py").read_text(encoding="utf-8")

    assert '"sentiment_report"' in trader_source
    assert 'reports["sentiment_report"] = state["social_report"]' in trader_source
    assert "extract_content(all_reports.get(\"sentiment_report\", \"\"))" in adapter_source
    assert "One sentence conclusion" in adapter_source
    assert "Historical transaction records" in adapter_source