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


def test_research_brief_index_and_sector_builders_keep_explicit_tool_workflow() -> None:
    module = _load_module(
        "scripts/template_upgrades/update_research_brief_v2_prompts.py",
        "update_research_brief_v2_prompts",
    )

    index_content = module.build_index_analyst_content("neutral")
    sector_content = module.build_sector_analyst_content("neutral")

    assert "get_market_overview" in index_content["tool_guidance"]
    assert "get_china_market_overview" in index_content["tool_guidance"]
    assert "get_index_data" in index_content["tool_guidance"]
    assert "The above parameter values must be used" in index_content["tool_guidance"]
    assert "Do not use other dates" in index_content["tool_guidance"]
    assert "Research caliber" in index_content["system_prompt"]
    assert "Research caliber" in index_content["user_prompt"]
    assert "A neutral perspective explains market status" in index_content["user_prompt"]
    assert "A factual balance of trends, funds, sentiment, cycles and evidence for and against" in index_content["user_prompt"]
    assert "Data conflicts, anomalies, missing or insufficient evidence" in index_content["analysis_requirements"]
    assert "Do not set it up separately Data gap statement Chapter" in index_content["analysis_requirements"]
    assert "Insufficient evidence can only reduce the strength of the conclusion" in index_content["analysis_requirements"]
    assert "Market cycles and positive and negative evidence assessments only cite direct return and traceable indicators of tools" in index_content["analysis_requirements"]
    assert "There is an obvious mismatch between the two financing change fields and the current balance." in index_content["analysis_requirements"]
    assert "can only be left in the data description" in index_content["analysis_requirements"]
    assert "Not to be extrapolated to Moving average downward trend " in index_content["analysis_requirements"]
    assert "Technical labels or rule identification intervals are only rule descriptions and are not equivalent to market conclusions." in index_content["analysis_requirements"]
    assert "Factual indicators such as transaction volume, turnover rate, and the number of rising and falling companies are summarized by the model." in index_content["analysis_requirements"]
    assert "Allowed writing examples" in index_content["analysis_requirements"]
    assert "Example of writing across the line" in index_content["analysis_requirements"]
    assert "Short-term data performance is strong" in index_content["analysis_requirements"]
    assert "Emotional repair completed" in index_content["analysis_requirements"]
    assert "The total transaction volume was 2,324.635 billion yuan, with the Shanghai/Shenzhen market accounting for 41.2% and 41.2% respectively. 58.8%" in index_content["analysis_requirements"]
    assert "If the data on financing and financing are incomplete, it should be clearly stated that they will not be included in the comprehensive assessment of funding." in index_content["analysis_requirements"]
    assert "Technical indicators are generally bullish, but high indicators suggest that we still need to pay attention to fluctuations in the short term." in index_content["analysis_requirements"]
    assert "The detailed list of daily limit and daily limit shows 59 companies at the daily limit, 8 companies at the daily limit, and 17 companies at the continuous limit." in index_content["analysis_requirements"]
    assert "Transaction activity increased significantly" in index_content["analysis_requirements"]
    assert "Unable to confirm leveraged fund attitude" in index_content["analysis_requirements"]
    assert "All three indicators show bullish signals" in index_content["analysis_requirements"]
    assert "Financing balances at cautious levels" in index_content["analysis_requirements"]
    assert "81 companies reached daily limit (including 59 companies with daily limit)" in index_content["analysis_requirements"]
    assert "Do not use space  stand firm  breakthrough " in index_content["analysis_requirements"]
    assert "Do not write PE/PB, dividend yield, valuation quantile" in index_content["analysis_requirements"]
    assert "Can only be used as data description" in index_content["user_prompt"]
    assert "Do not extend yourself into a moving average slope, style switch or high-level adjustment narrative" in index_content["user_prompt"]
    assert "The technical labels or rule intervals returned by the tool can only be used as descriptive clues and should not be directly rewritten into qualitative market conclusions." in index_content["user_prompt"]
    assert "use Short-term data performance is strong substitute Emotional repair completed " in index_content["user_prompt"]
    assert "use Factual data on total turnover, average turnover per listed company and turnover rate substitute Transaction activity increased significantly " in index_content["user_prompt"]
    assert "use Unable to confirm the direction of leverage funds substitute Unable to confirm leveraged fund attitude " in index_content["user_prompt"]
    assert "use Technical indicators are overall bullish substitute All three indicators show bullish signals " in index_content["user_prompt"]
    assert "When the two integrations are complete, only the balance and change values will be quoted; if the data is incomplete, it will be directly stated that it will not be included in the comprehensive assessment." in index_content["user_prompt"]
    assert "The number of companies with daily price limit and price limit should be consistent with the detailed list of price limit and price limit, do not mix them. `pct_chg` Threshold approximation results" in index_content["user_prompt"]
    assert "Data gap statement" not in index_content["system_prompt"]
    assert "PE、PB" not in index_content["system_prompt"]
    assert "Data gap statement" not in index_content["user_prompt"]
    assert "PE/PB" not in index_content["user_prompt"]
    assert "actual data date" not in index_content["system_prompt"]

    assert "get_sector_data" in sector_content["tool_guidance"]
    assert "get_peer_comparison" in sector_content["tool_guidance"]
    assert "get_fund_flow_data" in sector_content["tool_guidance"]
    assert "The above parameter values must be used" in sector_content["tool_guidance"]
    assert "Do not use another stock symbol or date" in sector_content["tool_guidance"]
    assert "Research caliber" in sector_content["system_prompt"]
    assert "Adhere to the research caliber" in sector_content["system_prompt"]
    assert "Reasons should be explained for trend judgment" in sector_content["system_prompt"]
    assert "Exception fields are not allowed to enter the comprehensive judgment" in sector_content["system_prompt"]
    assert "Industry labels must be processed in layers" in sector_content["system_prompt"]
    assert "only anchor point" in sector_content["system_prompt"]
    assert "Stock basic industry field (single value industry)" in sector_content["system_prompt"]
    assert "Limited industry knowledge can only be used as background explanation." in sector_content["system_prompt"]
    assert "Segmented industry labels that are closer to the main business" in sector_content["tool_guidance"]
    assert "The only main industry anchor" in sector_content["tool_guidance"]
    assert "If you cite a small amount of industry knowledge" in sector_content["tool_guidance"]
    assert "Significant allocation of main funds" in sector_content["tool_guidance"]
    assert "Individual stock capital flow return data" in sector_content["tool_guidance"]
    assert "Research caliber" in sector_content["user_prompt"]
    assert "The only main industry anchor" in sector_content["user_prompt"]
    assert "Allow a small amount of industry knowledge as background" in sector_content["user_prompt"]
    assert "Closer to the industry caliber of the main business" in sector_content["user_prompt"]
    assert "Did not enter the forefront of industry net capital inflows on the day" in sector_content["user_prompt"]
    assert "Individual stock capital flow return data" in sector_content["user_prompt"]
    assert "Not among the top net inflows of individual stocks on the day" in sector_content["user_prompt"]
    assert "Interest rates, regulation, asset quality, interest spreads, NPL ratio, provision coverage ratio" in sector_content["user_prompt"]
    assert "Margin of safety, recovery window or sector opportunity narrative" in sector_content["user_prompt"]
    assert "Mature stage, limited room for growth" in sector_content["user_prompt"]
    assert "Asset quality concerns/pressure from narrowing interest rate spreads" in sector_content["user_prompt"]
    assert "Capital flow and market popularity" in sector_content["analysis_requirements"]
    assert "Fact-based balanced assessment of risks and structural characteristics" in sector_content["analysis_requirements"]
    assert "Trend, prosperity, competition, rotation, valuation differentiation and capital flow judgment" in sector_content["analysis_requirements"]
    assert "Do not set it up separately Data gap statement Chapter" in sector_content["analysis_requirements"]
    assert "For all A-share stocks, the text can only retain one main industry affiliation." in sector_content["analysis_requirements"]
    assert "If the same stock hits multiple industry indexes" in sector_content["analysis_requirements"]
    assert "Bank stocks hit simultaneously Finance(A shares) " in sector_content["analysis_requirements"]
    assert "Allow a small amount of industry knowledge as background" in sector_content["analysis_requirements"]
    assert "Did not enter the forefront of industry net capital inflows on the day" in sector_content["analysis_requirements"]
    assert "Individual stock capital flow return data" in sector_content["analysis_requirements"]
    assert "margin of safety" in sector_content["analysis_requirements"]
    assert "Mature development stage, industry growth space is limited" in sector_content["analysis_requirements"]
    assert "Asset quality concerns and pressure from narrowing interest rate margins" in sector_content["analysis_requirements"]
    assert "Industry opportunities and risks" not in sector_content["user_prompt"]


def test_research_mode_migration_preserves_index_and_sector_tool_instructions() -> None:
    module = _load_module(
        "scripts/compliance/migrate_prompt_templates_to_research_mode.py",
        "migrate_prompt_templates_to_research_mode",
    )

    index_guidance = module.get_field_override("index_analyst", "tool_guidance")
    sector_guidance = module.get_field_override("sector_analyst", "tool_guidance")
    index_system_prompt = module.get_field_override("index_analyst", "system_prompt")
    sector_system_prompt = module.get_field_override("sector_analyst", "system_prompt")

    assert index_guidance is not None
    assert sector_guidance is not None
    assert index_system_prompt is not None
    assert sector_system_prompt is not None

    assert "get_market_overview" in index_guidance
    assert "get_index_data" in index_guidance
    assert "You must first call the tool to obtain the data" in index_guidance
    assert "Research caliber" in index_system_prompt
    assert "Adhere to the research caliber" in index_system_prompt
    assert "Determine the cause" in index_system_prompt
    assert "Data gap statement" not in index_system_prompt
    assert "PE、PB" not in index_system_prompt
    assert "PE/PB" not in index_guidance
    index_requirements = module.get_field_override("index_analyst", "analysis_requirements")
    assert index_requirements is not None
    assert "Market trends and technical patterns" in index_requirements
    assert "Fund flow direction (northbound, financing and financing)" in index_requirements
    assert "Trend judgment must also explain the corresponding data basis and the reasons for the formation." in index_requirements
    assert "Data conflicts, anomalies, missing or insufficient evidence" in index_requirements
    assert "Do not set it up separately Data gap statement Chapter" in index_requirements
    assert "Market cycles and positive and negative evidence assessments only cite direct return and traceable indicators of tools" in index_requirements
    assert "There is an obvious mismatch between the two financing change fields and the current balance." in index_requirements
    assert "can only be left in the data description" in index_requirements
    assert "Not to be extrapolated to Moving average downward trend " in index_requirements
    assert "Technical labels or rule identification intervals are only rule descriptions and are not equivalent to market conclusions." in index_requirements
    assert "Factual indicators such as transaction volume, turnover rate, and the number of rising and falling companies are summarized by the model." in index_requirements
    assert "Allowed writing examples" in index_requirements
    assert "Example of writing across the line" in index_requirements
    assert "The total transaction volume was 2,324.635 billion yuan, with the Shanghai/Shenzhen market accounting for 41.2% and 41.2% respectively. 58.8%" in index_requirements
    assert "If the data on financing and financing are incomplete, it should be clearly stated that they will not be included in the comprehensive assessment of funding." in index_requirements
    assert "Technical indicators are generally bullish, but high indicators suggest that we still need to pay attention to fluctuations in the short term." in index_requirements
    assert "The detailed list of daily limit and daily limit shows 59 companies at the daily limit, 8 companies at the daily limit, and 17 companies at the continuous limit." in index_requirements
    assert "Do not use space  stand firm  breakthrough " in index_requirements
    assert "Do not write PE/PB, dividend yield, valuation quantile" in index_requirements

    assert "get_sector_data" in sector_guidance
    assert "get_peer_comparison" in sector_guidance
    assert "You must first call the tool to obtain the data" in sector_guidance
    assert "The only main industry anchor" in sector_guidance
    assert "Research caliber" in sector_system_prompt
    assert "Determine the cause" in sector_system_prompt
    assert "Hierarchy label" in sector_system_prompt
    assert "Stock basic industry field (single value industry)" in sector_system_prompt
    assert "Allow a small amount of industry knowledge as background" in sector_system_prompt
    assert "actual data date" not in sector_system_prompt
    assert "Individual stock capital flow return data" in sector_guidance
    assert "If you cite a small amount of industry knowledge" in sector_guidance
    sector_requirements = module.get_field_override("sector_analyst", "analysis_requirements")
    assert sector_requirements is not None
    assert "Capital flow and market popularity" in sector_requirements
    assert "factual balanced assessment" in sector_requirements
    assert "Trend, prosperity, competition, rotation, valuation differentiation and capital flow judgment" in sector_requirements
    assert "Do not set it up separately Data gap statement Chapter" in sector_requirements
    assert "For all A-share stocks, the text can only retain one main industry affiliation." in sector_requirements
    assert "If the same stock hits multiple industry indexes" in sector_requirements
    assert "Closer to the industry caliber of the main business" in sector_requirements
    assert "Allow a small amount of industry knowledge as background" in sector_requirements
    assert "Did not enter the forefront of industry net capital inflows on the day" in sector_requirements
    assert "Not among the top net inflows of individual stocks on the day" in sector_requirements


def test_runtime_analyst_prompt_avoids_missing_dimension_sections() -> None:
    source = (ROOT / "core/agents/analyst.py").read_text(encoding="utf-8")

    assert "Do not list it separately Unobtained data dimensions " in source
    assert "This report did not obtain the following dimension data and does not conduct relevant analysis." in source
    assert "KOL Opinions, retail investor sentiment, institutional positions, industry capital flows" in source
    assert "If the tool returns Summary caliber/detailed caliber " in source
    assert "Both sets of values must be retained and clearly written out There is a caliber difference " in source
    assert "The data in this dimension is missing and will not be analyzed for the time being." not in source


def test_index_fallback_prompts_drop_information_gap_wording() -> None:
    source = (ROOT / "core/agents/adapters/index_analyst_v2.py").read_text(encoding="utf-8")

    assert "Key observation signals and subsequent verification matters" in source
    assert "Key macro signals and follow-up observations" in source
    assert "5. Key observation signals, information gaps and follow-up verification matters" not in source
    assert "3. Key macro signals, information gaps and follow-up observations" not in source


def test_sector_fallback_prompt_limits_background_industry_inference() -> None:
    source = (ROOT / "core/agents/adapters/sector_analyst_v2.py").read_text(encoding="utf-8")

    assert "Allow a small amount of industry knowledge as background" in source
    assert "Explicitly marked as background" in source
    assert "The industry is in a mature stage and has limited room for growth." in source
    assert "Valuation discount reflects concerns about asset quality and pressure to narrow interest margins" in source