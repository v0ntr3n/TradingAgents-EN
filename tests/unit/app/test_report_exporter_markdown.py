from app.utils.report_exporter import ReportExporter


def test_generate_markdown_report_hides_internal_module_keys_and_role_ids():
	exporter = ReportExporter()
	report_doc = {
		"stock_symbol": "000001",
		"analysis_date": "2026-04-11 00:00:00",
		"analysts": [
			"market_analyst",
			"bull_researcher",
			"risky_analyst",
		],
		"research_depth": "fast",
		"summary": "Here is the summary.",
		"reports": {
			"market_report": "## core observation\n\n Here is the market technology research content.",
			"trader_investment_plan": "## Research summary\n\n Here is the user version of the research briefing.",
			"final_trade_decision": "## Comprehensive research conclusion\n\n Here is the comprehensive research conclusion.\n\n**Disclaimer**: Please make independent judgment based on your own situation. Investment is risky and decisions need to be made with caution. Please consult professional advisors if necessary.",
			"bull_researcher": "## core proposition\n\n Here is the optimistic scenario argument.",
			"risky_analyst": "## Scenario conclusion\n\n Here s what the high-resilience scenario assessment looks like.",
		},
	}

	markdown_content = exporter.generate_markdown_report(report_doc)

	assert "bull_researcher" not in markdown_content
	assert "trader_investment_plan" not in markdown_content
	assert "final_trade_decision" not in markdown_content
	assert "risky_analyst" not in markdown_content
	assert "**analyst**: Market Technical Analyst, optimistic scenario argument, Highly resilient scenario assessment" in markdown_content
	assert "## 🧩 User version research briefing" in markdown_content
	assert "## 📝 Comprehensive research conclusion" in markdown_content
	assert "## 🌤️ optimistic scenario argument" in markdown_content
	assert "## ⚡ Highly resilient scenario assessment" in markdown_content
	assert markdown_content.index("## 🧩 User version research briefing") < markdown_content.index("## 📝 Comprehensive research conclusion")
	assert markdown_content.index("## 🧩 User version research briefing") < markdown_content.index("## 📈 Market Technology Research Report")
	assert "## Comprehensive research conclusion" not in markdown_content
	assert "### core observation" in markdown_content
	assert "Investment is risky and decisions need to be made with caution" not in markdown_content
	assert "This report is for research reference only and does not constitute individual stock recommendation, investment advice or operation basis. Please make independent judgments based on public information disclosure and your own research." in markdown_content


def test_generate_markdown_report_normalizes_chinese_numbered_subsections():
	exporter = ReportExporter()
	report_doc = {
		"stock_symbol": "000001",
		"analysis_date": "2026-04-11 00:00:00",
		"research_depth": "fast",
		"reports": {
			"index_report": "## 1. Core Observations\n\n Volume can rebound but structural differentiation remains.\n\n 2. Follow-up attention\n\n Pay attention to policy catalysis and transaction sustainability.",
			"sector_report": "**1. Prosperity clues**\n\n The plate rotation speed is accelerated.\n\n**2. Key points of verification**\n\n Observe whether the main line transactions continue.",
		},
	}

	markdown_content = exporter.generate_markdown_report(report_doc)

	assert "## 📊 Market Environment Research Report" in markdown_content
	assert "## 🏭 Industry sector research report" in markdown_content
	assert "### core observation" in markdown_content
	assert "### Follow up" in markdown_content
	assert "### Business clues" in markdown_content
	assert "### Verification points" in markdown_content
	assert "### 1. Core Observations" not in markdown_content
	assert "### 2. Follow-up attention" not in markdown_content
	assert "1. Prosperity clues" not in markdown_content
	assert "2. Key points of verification" not in markdown_content
