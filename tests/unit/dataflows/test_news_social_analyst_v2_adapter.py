def test_news_execute_uses_default_analysis_prompt(monkeypatch):
    from core.agents.adapters import news_analyst_v2 as module

    agent = module.NewsAnalystV2()
    agent._llm = object()
    agent._langchain_tools = [type("FakeTool", (), {"name": "get_stock_news_unified"})()]

    monkeypatch.setattr(module, "StockUtils", None)

    agent._build_system_prompt = lambda market_type=None, context=None, state=None: "SYSTEM"
    agent._build_user_prompt = lambda ticker, analysis_date, tool_data, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["analysis_prompt"] = analysis_prompt
        captured["message_count"] = len(messages)
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute(
        {
            "ticker": "000001",
            "analysis_date": "2026-04-13",
            "company_name": "Ping An Bank",
        }
    )

    assert result["news_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["message_count"] == 2


def test_news_default_analysis_prompt_contains_legacy_structure_guards():
    from core.agents.adapters import news_analyst_v2 as module

    agent = module.NewsAnalystV2()
    prompt = agent._build_analysis_prompt("000001")

    assert "Latest news summary" in prompt
    assert "News impact analysis" in prompt
    assert "Market Sentiment Assessment" in prompt
    assert "analysis point of view" in prompt
    assert "Multiple headlines essentially describing the same event" in prompt
    assert "short term response expectations" in prompt
    assert "No need for separate chapters" in prompt
    assert "Do not output investment recommendations, target prices, price ranges, positions, or execution plans" in prompt


def test_social_execute_uses_default_analysis_prompt(monkeypatch):
    from core.agents.adapters import social_analyst_v2 as module

    agent = module.SocialMediaAnalystV2()
    agent._llm = object()
    agent._langchain_tools = [type("FakeTool", (), {"name": "get_stock_sentiment_unified"})()]

    monkeypatch.setattr(module, "StockUtils", None)

    agent._build_system_prompt = lambda market_type=None, context=None, state=None: "SYSTEM"
    agent._build_user_prompt = lambda ticker, analysis_date, tool_data, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["analysis_prompt"] = analysis_prompt
        captured["message_count"] = len(messages)
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute(
        {
            "ticker": "000001",
            "analysis_date": "2026-04-13",
            "company_name": "Ping An Bank",
        }
    )

    assert result["sentiment_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["message_count"] == 2


def test_social_default_analysis_prompt_contains_dimension_guards():
    from core.agents.adapters import social_analyst_v2 as module

    agent = module.SocialMediaAnalystV2()
    prompt = agent._build_analysis_prompt("000001")

    assert "If the tool explicitly states that the current results are from news fallback sentiment summaries" in prompt
    assert "Do not analyze this dimension" in prompt
    assert "Do not use The emotional turning point has arrived " in prompt
    assert "Do not output investment recommendations, target prices, price ranges, positions, or execution plans" in prompt
