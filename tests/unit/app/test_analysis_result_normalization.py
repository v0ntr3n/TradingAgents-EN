from app.routers.analysis import has_meaningful_result_payload, normalize_result_data


def test_normalize_result_data_preserves_full_reports_for_detail_endpoints():
	raw_market_report = "# Market technical analysis\n\n This is complete technical market analysis content and should not be compressed in the details interface.\n\n- observation point A\n- observation point B"
	raw_research_report = "# Optimistic Scenario Researcher\n\n This is the complete optimistic scenario argument and should not be filtered out."

	result = normalize_result_data(
		{
			"summary": "Full summary",
			"recommendation": "Complete research conclusion",
			"reports": {
				"market_report": raw_market_report,
				"bull_researcher": raw_research_report,
			},
		}
	)

	assert result["summary"] == "Full summary"
	assert result["recommendation"] == "Complete research conclusion"
	assert result["reports"]["market_report"] == raw_market_report
	assert result["reports"]["bull_researcher"] == raw_research_report


def test_normalize_result_data_builds_final_decision_report_when_missing():
	result = normalize_result_data(
		{
			"reports": {
				"fundamentals_report": "# fundamental analysis\n\n Here is the complete fundamental analysis."
			},
			"decision": {
				"analysis_view": "Neutral",
				"confidence": 0.75,
				"risk_score": 0.62,
				"summary": "The current situation is closer to the baseline scenario.",
				"reasoning": "The main basis comes from interest spreads, asset quality and valuation constraints.",
				"risk_warning": "It is necessary to continue to pay attention to changes in the defective rate.",
				"watch_items": ["Quarterly spread changes", "Retail overdue rate"],
			},
		}
	)

	assert "final_trade_decision" in result["reports"]
	assert "Research Judgment: Neutral" in result["reports"]["final_trade_decision"]
	assert "Mainly based on interest spread, asset quality and valuation constraints" in result["reports"]["final_trade_decision"]
	assert "Quarterly spread changes" in result["reports"]["final_trade_decision"]


def test_normalize_result_data_demotes_inferential_core_evidence_in_decision():
	result = normalize_result_data(
		{
			"decision": {
				"analysis_view": "Neutral",
				"reasoning": "It is currently more appropriate to wait for annual report disclosures.",
				"core_evidence": ["PB is 0.48 times", "The proportion of retail loans is inferred to exceed 60%"],
				"uncertainties": ["Net interest margin data is missing"],
				"watch_items": ["Next financial report"],
			},
		}
	)

	assert result["decision"]["core_evidence"] == ["PB is 0.48 times"]
	assert "The proportion of retail loans is inferred to exceed 60%" in result["decision"]["uncertainties"]


def test_has_meaningful_result_payload_rejects_empty_shell_result():
	assert has_meaningful_result_payload(
		{
			"summary": "",
			"recommendation": "",
			"reports": {},
			"decision": {},
			"key_points": [],
		}
	) is False


def test_has_meaningful_result_payload_accepts_report_backed_result():
	assert has_meaningful_result_payload(
		{
			"summary": "",
			"recommendation": "",
			"reports": {
				"market_report": "# Market technical analysis\n\n This is valid reporting content."
			},
			"decision": {},
			"key_points": [],
		}
	) is True
