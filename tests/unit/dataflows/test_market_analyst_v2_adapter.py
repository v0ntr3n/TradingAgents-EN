def test_build_user_prompt_keeps_state_company_name_when_market_lookup_empty(monkeypatch):
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    captured = {}

    class FakeStockUtils:
        @staticmethod
        def get_market_info(ticker):
            return {
                "market_name": "China A shares",
                "currency_name": "RMB",
                "currency_symbol": "¥",
                "company_name": "",
            }

    def fake_get_prompt_from_template(*args, **kwargs):
        captured["variables"] = kwargs["variables"]
        return "PROMPT"

    monkeypatch.setattr(module, "StockUtils", FakeStockUtils)
    agent._get_company_name = lambda ticker, market_info: ""
    agent._get_prompt_from_template = fake_get_prompt_from_template

    prompt = agent._build_user_prompt(
        ticker="000001",
        analysis_date="2026-04-13",
        state={"company_name": "Ping An Bank"},
    )

    assert prompt == "PROMPT"
    assert captured["variables"]["company_name"] == "Ping An Bank"


def test_execute_uses_default_analysis_prompt(monkeypatch):
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    agent._llm = object()
    agent._langchain_tools = [type("FakeTool", (), {"name": "get_stock_market_data_unified"})()]

    monkeypatch.setattr(module, "StockUtils", None)

    agent._build_system_prompt = lambda market_type=None, context=None, state=None: "SYSTEM"
    agent._build_user_prompt = lambda ticker, analysis_date, state: "USER"
    agent._build_analysis_prompt = lambda ticker: "ANALYSIS"

    captured = {}

    def fake_invoke_with_tools(messages, analysis_prompt=None, max_iterations=3):
        captured["analysis_prompt"] = analysis_prompt
        captured["message_count"] = len(messages)
        return "REPORT"

    agent.invoke_with_tools = fake_invoke_with_tools

    result = agent.execute({
        "ticker": "000001",
        "analysis_date": "2026-04-13",
        "company_name": "Ping An Bank",
    })

    assert result["market_report"] == "REPORT"
    assert captured["analysis_prompt"] == "ANALYSIS"
    assert captured["message_count"] == 2


def test_default_analysis_prompt_contains_latest_observation_guards():
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    prompt = agent._build_analysis_prompt("000001")

    assert "It is forbidden to write the analysis date directly as the actual data date" in prompt
    assert "Not yet firmly above MA5" in prompt
    assert "Does the histogram appear to be continuously enlarged?" in prompt
    assert "There is some room for upside" in prompt
    assert "A word-by-word self-check must be done before output" in prompt


def test_sanitize_report_removes_threshold_language():
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    original = (
        "The price has not yet reached MA5 and cannot effectively stand above it. It has not broken through the Bollinger Band upper limit, and the upside space is limited.\n"
        "1. Whether the price deviation from MA5 has converged and whether it can effectively stabilize.\n"
        "2. MACD Whether the positive value state continues, and whether the histogram continues to expand or shrink."
    )

    sanitized = agent._sanitize_report(original)

    assert "stand on" not in sanitized
    assert "stand firm" not in sanitized
    assert "Effective breakthrough" not in sanitized
    assert "Keep zooming in" not in sanitized
    assert "Upside" not in sanitized
    assert "Breaking through the Bollinger Band track" not in sanitized
    assert "still below MA5" in sanitized
    assert "Is the short-term moving average relationship improving?" in sanitized
    assert "Whether kinetic energy consistency increases or decreases" in sanitized


def test_sanitize_report_keeps_breakout_rewrite_fluent():
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    original = "The position of Bollinger Bands only shows that the current price is in a relatively high range and has not yet formed an effective breakthrough signal."

    sanitized = agent._sanitize_report(original)

    assert sanitized == "The position of Bollinger Bands only shows that the current price is in a relatively high range, and there is still insufficient basis for a breakout."


def test_sanitize_report_rewrites_snapshot_as_relationships():
    from core.agents.adapters import market_analyst_v2 as module

    agent = module.MarketAnalystV2()
    original = (
        "The price has not yet broken through MA5, indicating that the short-term momentum recovery has not yet completed the confirmation of the short-term moving average."
        "This range has narrowed compared with the previous period, indicating that short-term fluctuations tend to converge."
        "The short-term moving average system has an upward trend, but it lacks upward breakthrough momentum."
    )

    sanitized = agent._sanitize_report(original)

    assert "Not yet broken through MA5" not in sanitized
    assert "Confirmation above short-term moving average" not in sanitized
    assert "Slightly narrower than the previous period" not in sanitized
    assert "Sort trends upwards" not in sanitized
    assert "Upward breakout momentum" not in sanitized
    assert "still below MA5" in sanitized
    assert "Confirmation of improved relationship with short-term moving averages" in sanitized
    assert "Shows that short-term fluctuations are concentrated within the current range" in sanitized
    assert "strong-biased arrangement" in sanitized
    assert "Basis for further strengthening" in sanitized