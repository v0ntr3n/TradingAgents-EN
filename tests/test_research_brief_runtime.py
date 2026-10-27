from app.utils.compliance import (
    sanitize_analysis_payload,
    sanitize_display_report_text,
    sanitize_report_artifacts,
    sanitize_position_analysis_payload,
    sanitize_trade_review_payload,
)
from app.utils.report_formatter import (
    _convert_json_to_markdown,
    _convert_final_decision_json_to_markdown,
    format_decision,
)


def test_sanitize_analysis_payload_strips_legacy_execution_fields() -> None:
    raw_result = {
        "summary": "It is recommended to buy, with a target price of 100 yuan and a position of 20%.",
        "reports": {
            "market_report": "The company s orders have picked up and profitability has improved, but it still needs to track the fluctuations in raw materials in the future.",
            "final_trade_decision": "It is recommended to buy and pay attention to the target price of 100 yuan.",
        },
        "decision": {
            "action": "BUY",
            "confidence": 82,
            "risk_score": 65,
            "target_price": 100,
            "price_analysis_range": [90, 100],
            "risk_exposure_ratio": "20%",
            "stop_loss": 88,
            "reasoning": "Orders have picked up, gross profit margins have recovered, and cash flow has improved.",
            "summary": "The trend of profit restoration continues, but cost pressures still need to be paid attention to.",
            "risk_warning": "Fluctuations in raw material prices can erode profits.",
            "core_evidence": ["Orders pick up", "Gross profit margin repair"],
            "uncertainties": ["Continuity of demand"],
            "invalidation_conditions": ["Orders drop again"],
            "watch_items": ["Next financial report"],
        },
    }

    sanitized = sanitize_analysis_payload(raw_result)

    assert sanitized["reports"] == {
        "market_report": "The company s orders have picked up and profitability has improved, but it still needs to track the fluctuations in raw materials in the future."
    }
    assert sanitized["decision"]["action"] == "optimistic"
    assert sanitized["decision"]["analysis_view"] == "optimistic"
    assert sanitized["decision"]["confidence"] == 0.82
    assert sanitized["decision"]["risk_score"] == 0.65
    assert sanitized["decision"]["core_evidence"] == ["Orders pick up", "Gross profit margin repair"]
    assert sanitized["decision"]["uncertainties"] == ["Continuity of demand"]
    assert sanitized["decision"]["invalidation_conditions"] == ["Orders drop again"]
    assert sanitized["decision"]["watch_items"] == ["Next financial report"]
    assert "target_price" not in sanitized["decision"]
    assert "price_analysis_range" not in sanitized["decision"]
    assert "risk_exposure_ratio" not in sanitized["decision"]
    assert "stop_loss" not in sanitized["decision"]
    assert sanitized["recommendation"].startswith("Research Judgment: Optimistic;")
    assert "target price" not in sanitized["recommendation"]
    assert "position" not in sanitized["recommendation"]


def test_format_decision_keeps_research_brief_fields_only() -> None:
    decision = format_decision(
        {
            "action": "BUY",
            "confidence": 0.78,
            "risk_score": 0.32,
            "target_price": 120,
            "position_ratio": "15%",
            "reasoning": "Improved demand has led to upward revisions to earnings expectations.",
            "summary": "The current evidence is biased towards optimism, but the pace of realization needs to be continued.",
            "risk_warning": "If the demand recovery is less than expected, the judgment may weaken.",
            "core_evidence": ["Demand improvement", "Earnings forecast revised upwards"],
            "uncertainties": ["deliver rhythm"],
            "invalidation_conditions": ["Economic sentiment weakens again"],
            "watch_items": ["monthly sales data"],
        }
    )

    assert decision == {
        "action": "optimistic",
        "analysis_view": "optimistic",
        "confidence": 0.78,
        "risk_score": 0.32,
        "reasoning": "Improved demand has led to upward revisions to earnings expectations.",
        "summary": "The current evidence is biased towards optimism, but the pace of realization needs to be continued.",
        "risk_warning": "If the demand recovery is less than expected, the judgment may weaken.",
        "core_evidence": ["Demand improvement", "Earnings forecast revised upwards"],
        "uncertainties": ["deliver rhythm"],
        "invalidation_conditions": ["Economic sentiment weakens again"],
        "watch_items": ["monthly sales data"],
    }


def test_format_decision_demotes_inferential_core_evidence() -> None:
    decision = format_decision(
        {
            "action": "HOLD",
            "confidence": 0.66,
            "risk_score": 0.41,
            "reasoning": "The current key differences still need to be verified by more complete disclosure.",
            "core_evidence": ["ROE Four consecutive quarters of recovery", "The proportion of retail loans is inferred to exceed 60%"],
            "uncertainties": ["The direction of change in net interest margin was not disclosed"],
            "watch_items": ["Next financial report"],
        }
    )

    assert decision["core_evidence"] == ["ROE Four consecutive quarters of recovery"]
    assert "The proportion of retail loans is inferred to exceed 60%" in decision["uncertainties"]


def test_convert_final_decision_json_to_markdown_uses_research_brief_sections() -> None:
    markdown = _convert_final_decision_json_to_markdown(
        {
            "risk_level": "in",
            "risk_score": 0.4,
            "final_trade_decision": {
                "analysis_view": "Neutral",
                "confidence": 72,
                "target_price": 88,
                "risk_control_reference": 75,
                "risk_exposure_ratio": "10%",
                "reasoning": "The current evidence is not enough to support a clearer direction, and operating data need to continue to be observed.",
                "summary": "The judgment remains neutral and awaits more operational verification.",
                "core_evidence": ["Earnings performance stabilizes"],
                "uncertainties": ["demand recovery slope"],
                "invalidation_conditions": ["Earnings worsen again"],
                "watch_items": ["Next issue operating disclosure"],
                "risk_warning": "If industry demand continues to weaken, the conclusion may be revised downwards.",
            },
        }
    )

    assert "# 🎯 Comprehensive research conclusion" in markdown
    assert "- **research perspective**: ⚪ Neutral" in markdown
    assert "## 🔍 core basis" in markdown
    assert "## ❓ key uncertainties" in markdown
    assert "## 🔄 Determine adjustment conditions" in markdown
    assert "## 👀 Follow-up observations" in markdown
    assert "Observation interval reference" not in markdown
    assert "key verification bit" not in markdown
    assert "Risk tolerance premise" not in markdown


def test_convert_final_decision_json_to_markdown_reindexes_non_empty_lists() -> None:
    markdown = _convert_final_decision_json_to_markdown(
        {
            "final_trade_decision": {
                "analysis_view": "Neutral",
                "core_evidence": ["evidence A", "", None, "evidence B"],
                "uncertainties": [None, "uncertainty A"],
                "invalidation_conditions": ["Conditions A", "", "Conditions B"],
                "watch_items": ["Observations A", None, "Observations B"],
            }
        }
    )

    assert "1. evidence A" in markdown
    assert "2. evidence B" in markdown
    assert "3. evidence B" not in markdown
    assert "1. uncertainty A" in markdown
    assert "1. Conditions A" in markdown
    assert "2. Conditions B" in markdown
    assert "1. Observations A" in markdown
    assert "2. Observations B" in markdown


def test_sanitize_display_report_text_normalizes_legacy_disclaimer() -> None:
    raw_text = """## Comprehensive research conclusion

The current judgment still needs to be verified in conjunction with subsequent disclosures.

**Disclaimer**: Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary.
"""

    sanitized = sanitize_display_report_text(raw_text)

    assert "The current judgment still needs to be verified in conjunction with subsequent disclosures." in sanitized
    assert "Investment is risky and decisions need to be made with caution" not in sanitized
    assert "This report is for research reference only and does not constitute individual stock recommendation, investment advice or operation basis. Please make independent judgments based on public information disclosure and your own research." in sanitized


def test_sanitize_display_report_text_removes_price_and_actionable_lines() -> None:
    raw_text = """## Scenario conclusion

Current judgment still relies on verification of subsequent financial reports and operating data.

- The price center may move up to the 12.8-13.5 yuan range
- If it breaks through 11.33 yuan, it will strengthen upward expectations.
- It is recommended to maintain 60%-80% risk exposure

## public signal to continue verification

1. Will the next financial report disclose more complete asset quality data?
2. Are there any changes in regulatory standards?
"""

    sanitized = sanitize_display_report_text(raw_text)

    assert "Current judgment still relies on verification of subsequent financial reports and operating data." in sanitized
    assert "Will the next financial report disclose more complete asset quality data?" in sanitized
    assert "Are there any changes in regulatory standards?" in sanitized
    assert "12.8-13.5 meta interval" not in sanitized
    assert "Breaking through 11.33 yuan" not in sanitized
    assert "60%-80%risk exposure" not in sanitized


def test_sanitize_display_report_text_normalizes_legacy_titles_and_soft_investment_language() -> None:
    raw_text = """## News Analyst Research Report

This event may become the starting point for value restoration and has certain appeal to allocation investors.

## Sector Analyst Research Observation Report

The current industry discussion is on the rise, but it is more suitable as a follow-up research clue than an investment opportunity.
"""

    sanitized = sanitize_display_report_text(raw_text)

    assert "## Journalism Research" in sanitized
    assert "## Industry sector research" in sanitized
    assert "The starting point of value restoration" not in sanitized
    assert "allocation investor" not in sanitized
    assert "investment opportunities" not in sanitized
    assert "Early signs of valuation and expected repairs" in sanitized
    assert "research users" in sanitized
    assert "research leads" in sanitized


def test_sanitize_report_artifacts_removes_raw_news_tool_call_payload() -> None:
    raw_text = """## news research report

{"name": "get_stock_news_details_unified", "arguments": {"news_ids": "news_1,news_2"}}
</tool_call>
"""

    sanitized = sanitize_report_artifacts(raw_text)

    assert 'get_stock_news_details_unified' not in sanitized
    assert '</tool_call>' not in sanitized
    assert '## news research report' in sanitized


def test_sanitize_report_artifacts_downgrades_conflicting_stable_data_snapshot_date() -> None:
    raw_text = """### core observation
There is currently no stable post-closing daily frequency data corresponding to the analysis day (2026-04-21), so the historical valuation quantiles and peer comparisons are all based on the previous available trading day.
The snapshot date of all valuation indicators is unified to **2026-04-21**. 
"""

    sanitized = sanitize_report_artifacts(raw_text)

    assert 'The snapshot date of all valuation indicators is unified to **2026-04-21**' not in sanitized
    assert 'The current text date and caliber are still to be verified.' in sanitized


def test_convert_json_report_to_markdown_downgrades_error_payload_dict() -> None:
    markdown = _convert_json_to_markdown(
        "{'error': 'Request timed out.', 'success': False}",
        report_type="risk",
    )

    assert markdown == "The execution of the risk review module has not been completed, and the current risk conclusions still need to be verified."


def test_convert_json_report_to_markdown_downgrades_execution_failure_text() -> None:
    markdown = _convert_json_to_markdown(
        "Execution failed: LLM API Call failed (retried 0 times): Request timed out.",
        report_type="investment",
    )

    assert markdown == "The implementation of the comprehensive research conclusion module has not been completed, and the current conclusions still need to be verified."


def test_sanitize_position_analysis_payload_strips_execution_fields() -> None:
    raw_result = {
        "action": "add",
        "action_reason": "It is recommended to increase the position, stop loss if it falls below 9.8 yuan, and the target price is 12 yuan.",
        "summary": "It is recommended to continue to hold and wait for the target price of 12 yuan.",
        "detailed_analysis": "The company s fundamentals are stable, but if it falls below 9.8 yuan, it needs to stop losses.",
        "risk_assessment": "If industry sentiment continues to weaken, profitability will come under pressure.",
        "opportunity_assessment": "If asset quality improves, valuation recovery flexibility may increase.",
        "price_targets": {"stop_loss_price": 9.8, "take_profit_price": 12.0},
        "suggested_quantity": 1000,
        "suggested_amount": 10000,
        "confidence": 88,
    }

    sanitized = sanitize_position_analysis_payload(raw_result)

    assert sanitized["action"] == "hold"
    assert sanitized["price_targets"] == {}
    assert sanitized["suggested_quantity"] is None
    assert sanitized["suggested_amount"] is None
    assert sanitized["confidence"] == 88.0
    assert "Add to position" not in sanitized["action_reason"]
    assert "stop loss" not in sanitized["action_reason"]
    assert "target price" not in sanitized["summary"]
    assert sanitized["recommendation"].startswith("This position research only provides research observations")


def test_sanitize_analysis_payload_strips_news_and_sentiment_execution_language() -> None:
    raw_result = {
        "reports": {
            "news_report": "It is recommended to buy with a target price of 12 yuan.\n The company s announcement shows that the new production line has been put into production, and the pace of volume expansion still needs to be tracked in the future.",
            "sentiment_report": "Social media suggests adding to your position and setting a stop loss.\n Discussions are heating up, but the differences are clear and there is a lot of noise.",
        },
        "summary": "It is recommended to buy with a target price of 12 yuan.",
        "key_points": ["Recommended to buy", "New production line put into operation"],
    }

    sanitized = sanitize_analysis_payload(raw_result)

    assert "buy" not in sanitized["summary"]
    assert "target price" not in sanitized["summary"]
    assert "Company announcement shows new production line put into production" in sanitized["reports"]["news_report"]
    assert "Discussion heats up" in sanitized["reports"]["sentiment_report"]
    assert all("buy" not in point for point in sanitized["key_points"])


def test_sanitize_analysis_payload_demotes_inferential_core_evidence() -> None:
    raw_result = {
        "summary": "Awaiting further verification in the annual report.",
        "reports": {
            "market_report": "Prices are still in a volatile range."
        },
        "decision": {
            "analysis_view": "Neutral",
            "confidence": 68,
            "risk_score": 52,
            "reasoning": "It is currently more appropriate to maintain neutral research judgments based on disclosed data.",
            "core_evidence": ["PB is 0.48 times", "The proportion of retail loans is inferred to exceed 60%"],
            "uncertainties": ["Missing breakdown of non-performing loan ratio data"],
            "watch_items": ["Next financial report"],
        },
    }

    sanitized = sanitize_analysis_payload(raw_result)

    assert sanitized["decision"]["core_evidence"] == ["PB is 0.48 times"]
    assert "The proportion of retail loans is inferred to exceed 60%" in sanitized["decision"]["uncertainties"]


def test_sanitize_analysis_payload_strips_index_and_sector_execution_language() -> None:
    raw_result = {
        "reports": {
            "index_report": "It is recommended to pay attention to the support level of 3300 points and plan for dips.\n Liquidity is neutral, and policy rhythm still needs to be tracked.",
            "sector_report": "The new energy sector has allocation suggestions and safety margins.\n The prosperity of the industry has recovered, but the differentiation among peers is obvious.",
        },
        "summary": "It is recommended to pay attention to the support level of 3300 points and plan for dips.",
        "key_points": ["Configuration recommendations", "Restoration of industry prosperity"],
    }

    sanitized = sanitize_analysis_payload(raw_result)

    assert "support level" not in sanitized["summary"]
    assert "Configuration recommendations" not in sanitized["summary"]
    assert "Liquidity Neutral" in sanitized["reports"]["index_report"]
    assert "Restoration of industry prosperity" in sanitized["reports"]["sector_report"]
    assert all("Configuration recommendations" not in point for point in sanitized["key_points"])


def test_sanitize_trade_review_payload_strips_future_trade_actions() -> None:
    raw_result = {
        "summary": "Next time, you can buy it back near 10 yuan and increase your position to 50%.",
        "timing_analysis": "If it returns to 10.2 yuan, you can buy again. If it falls below 9.8 yuan, you should stop the loss.",
        "position_analysis": "It is recommended to increase the position to 50% next time and set a take profit.",
        "emotion_analysis": "Panic selling occurs, but can be improved with preset rules.",
        "attribution_analysis": "The gains this time come more from industry recovery than from stable timing capabilities.",
        "suggestions": ["Buy next time it drops to 10 yuan", "Position mentioned 50%"],
    }

    sanitized = sanitize_trade_review_payload(raw_result)

    assert "10 Yuan" not in sanitized["summary"]
    assert "buy" not in sanitized["timing_analysis"]
    assert "Add to position" not in sanitized["position_analysis"]
    assert all("buy" not in item for item in sanitized["suggestions"])
    assert all("50%" not in item for item in sanitized["suggestions"])
