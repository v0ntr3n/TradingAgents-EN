from app.utils.report_formatter import extract_reports_from_state, generate_summary_recommendation


def test_extract_reports_from_state_prefers_nested_reports_mapping():
    state = {
        "analysis_id": "demo-analysis",
        "reports": {
            "fundamentals_report": "# fundamental analysis\n\n The company s profitability has improved and its cash flow performance has been stable.",
            "neutral_analyst": "# Ping An Bank (000001) Scenario Balancing and Weight of Evidence Review Report\n\n## 1. Core Situation Judgment\n\n The current situation is closer to the baseline scenario.",
            "risk_management_decision": {
                "content": "# Risk Governance Summary\n\n## core risk\n\n It is necessary to continue to track changes in asset quality."
            },
        },
    }

    reports = extract_reports_from_state(state)

    assert "fundamentals_report" in reports
    assert "neutral_analyst" in reports
    assert "risk_management_decision" in reports
    assert "Improved profitability" in reports["fundamentals_report"]
    assert "core situational judgment" in reports["neutral_analyst"]
    assert "core risk" in reports["risk_management_decision"]


def test_generate_summary_recommendation_prefers_trader_brief_over_final_decision():
    reports = {
        "final_trade_decision": "# Comprehensive research conclusion\n\n This is an internal synthesis conclusion and should be used as a secondary fallback." * 4,
        "trader_investment_plan": "# User version research briefing\n\n One-sentence conclusion: The current situation is closer to neutral and more cautious. The follow-up focus will be on whether asset quality and transaction recovery continue.\n\n Why we think so: The valuation is not high, but the catalytic and verification data are not solid enough.",
    }

    summary, recommendation = generate_summary_recommendation(
        reports,
        {"action": "Neutral", "reasoning": "Waiting for more verification data."},
        "000001",
    )

    assert "One sentence conclusion" in summary
    assert "internal comprehensive conclusion" not in summary
    assert "Research opinion: Neutral" in recommendation