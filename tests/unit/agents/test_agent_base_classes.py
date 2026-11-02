"""
Test Agent base class implementation

The test is based on the specific implementation of 5 base classes Agent
Includes:
- Main process Agent (12 a)
- Position analysis Agent (4 a)
- Review analysis Agent (5 a)
"""

import pytest
from unittest.mock import Mock, MagicMock


def test_is_retryable_llm_error_recognizes_timed_out_variant() -> None:
    from core.agents.base import is_retryable_llm_error

    assert is_retryable_llm_error("Request timed out.") is True
    assert is_retryable_llm_error("The read operation timed out") is True
    assert is_retryable_llm_error("validation failed") is False


class TestMarketAnalystV2:
    """test market analyst V2"""
    
    def test_import(self):
        """Test import"""
        from core.agents.adapters import MarketAnalystV2
        assert MarketAnalystV2 is not None
    
    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import MarketAnalystV2

        assert MarketAnalystV2.metadata.id == "market_analyst_v2"
        assert MarketAnalystV2.metadata.name == "market analyst v2.0"
        assert MarketAnalystV2.analyst_type == "market"
        assert MarketAnalystV2.output_field == "market_report"
    
    def test_system_prompt(self):
        """Test system prompt word generation"""
        from core.agents.adapters import MarketAnalystV2
        
        agent = MarketAnalystV2()
        prompt = agent._build_system_prompt("A shares")
        
        assert "market analyst" in prompt
        assert "technical analysis" in prompt
    
    def test_user_prompt(self):
        """Test user prompt word generation"""
        from core.agents.adapters import MarketAnalystV2
        
        agent = MarketAnalystV2()
        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            state={"company_name": "Ping An Bank"}
        )
        
        assert "000001" in prompt
        assert "2024-12-15" in prompt
        assert "Ping An Bank" in prompt


class TestBullResearcherV2:
    """Testing Optimistic Scenario Researchers V2"""
    
    def test_import(self):
        """Test import"""
        from core.agents.adapters import BullResearcherV2
        assert BullResearcherV2 is not None
    
    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import BullResearcherV2

        assert BullResearcherV2.metadata.id == "bull_researcher_v2"
        assert BullResearcherV2.metadata.name == "Optimistic Scenario Researcher v2.0"
        assert BullResearcherV2.researcher_type == "bull"
        assert BullResearcherV2.stance == "bull"
    
    def test_required_reports(self):
        """List of reports required for testing"""
        from core.agents.adapters import BullResearcherV2
        
        agent = BullResearcherV2()
        reports = agent._get_required_reports()
        
        assert "market_report" in reports
        assert "news_report" in reports
        assert "fundamentals_report" in reports
    
    def test_user_prompt(self):
        """Test user prompt word generation"""
        from core.agents.adapters import BullResearcherV2
        
        agent = BullResearcherV2()
        prompt = agent._build_user_prompt(
            ticker="AAPL",
            analysis_date="2024-12-15",
            reports={
                "market_report": "The market is optimistic",
                "news_report": "good news"
            },
            historical_context=None,
            state={}
        )
        
        assert "AAPL" in prompt
        assert "optimistic" in prompt or "market" in prompt


class TestResearchManagerV2:
    """Test Research Manager V2"""
    
    def test_import(self):
        """Test import"""
        from core.agents.adapters import ResearchManagerV2
        assert ResearchManagerV2 is not None
    
    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import ResearchManagerV2

        assert ResearchManagerV2.metadata.id == "research_manager_v2"
        assert ResearchManagerV2.metadata.name == "research integrator v2.0"
        assert ResearchManagerV2.manager_type == "research"
        assert ResearchManagerV2.output_field == "investment_plan"
    
    def test_required_inputs(self):
        """List of inputs required for testing"""
        from core.agents.adapters import ResearchManagerV2
        
        agent = ResearchManagerV2()
        inputs = agent._get_required_inputs()
        
        assert "bull_report" in inputs
        assert "bear_report" in inputs
    
    def test_user_prompt(self):
        """Test user prompt word generation"""
        from core.agents.adapters import ResearchManagerV2
        
        agent = ResearchManagerV2()
        prompt = agent._build_user_prompt(
            ticker="AAPL",
            analysis_date="2024-12-15",
            inputs={
                "bull_report": "positive evidence",
                "bear_report": "cautious evidence"
            },
            debate_summary=None,
            state={}
        )
        
        assert "AAPL" in prompt
        assert "Positive" in prompt or "cautious" in prompt

    def test_delegate_to_agent_uses_compatible_invoke_path(self):
        """Testing delegated child agents no longer fails due to missing invoke_agent"""
        from unittest.mock import Mock, patch
        from core.agents.adapters import ResearchManagerV2

        mock_llm = Mock()
        mock_llm.invoke.return_value = Mock(content="Comprehensive conclusion: continue to observe")

        agent = ResearchManagerV2(llm=mock_llm)

        delegated_agent = Mock()
        delegated_agent.execute.return_value = {"chip_report": "High chip concentration"}

        with patch("core.agents.factory.AgentFactory.create_with_dynamic_tools", return_value=delegated_agent) as mock_create:
            result = agent._run_delegated_research_agents({
                "ticker": "600519",
                "analysis_date": "2026-05-11",
                "node_config": {
                    "delegated_agent_ids": ["chip_distribution_analyst_v2"],
                },
            })

        mock_create.assert_called_once_with("chip_distribution_analyst_v2", llm=mock_llm)
        delegated_agent.execute.assert_called_once()
        assert result == {"chip_report": "High chip concentration"}


class TestTraderV2:
    """Test Research Integrator V2"""
    
    def test_import(self):
        """Test import"""
        from core.agents.adapters import TraderV2
        assert TraderV2 is not None
    
    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import TraderV2

        assert TraderV2.metadata.id == "trader_v2"
        assert TraderV2.metadata.name == "research integrator v2.0"
        assert TraderV2.output_field == "trader_investment_plan"
    
    def test_user_prompt(self):
        """Test user prompt word generation"""
        from core.agents.adapters import TraderV2
        
        agent = TraderV2()
        prompt = agent._build_user_prompt(
            ticker="AAPL",
            analysis_date="2024-12-15",
            investment_plan={"recommendation": "optimistic"},
            all_reports={"market_report": "market analysis"},
            historical_trades=None,
            state={}
        )
        
        assert "AAPL" in prompt
        assert "optimistic" in prompt or "research plan" in prompt


# ============================================================
# Added analyst agent test
# ============================================================

class TestNewsAnalystV2:
    """Test News Analyst V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import NewsAnalystV2
        assert NewsAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import NewsAnalystV2

        assert NewsAnalystV2.metadata.id == "news_analyst_v2"
        assert NewsAnalystV2.metadata.name == "news analyst v2.0"
        assert NewsAnalystV2.analyst_type == "news"
        assert NewsAnalystV2.output_field == "news_report"

    def test_fallback_user_prompt_uses_research_observation_schema(self):
        """Test news analysts downgrade prompt words to research observation semantics"""
        from core.agents.adapters import NewsAnalystV2

        agent = NewsAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            tool_data={},
            state={"company_name": "Ping An Bank"},
        )

        assert "News event research" in prompt
        assert "Follow-up observations" in prompt
        assert "Judgment of Investment Opportunity Window" not in prompt


class TestSocialMediaAnalystV2:
    """Test social media analyst V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import SocialMediaAnalystV2
        assert SocialMediaAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import SocialMediaAnalystV2

        assert SocialMediaAnalystV2.metadata.id == "social_analyst_v2"
        assert SocialMediaAnalystV2.metadata.name == "social media analyst v2.0"
        assert SocialMediaAnalystV2.analyst_type == "social"
        assert SocialMediaAnalystV2.output_field == "sentiment_report"

    def test_fallback_user_prompt_uses_research_observation_schema(self):
        """Test social media analysts downgrade prompt words to research observation semantics"""
        from core.agents.adapters import SocialMediaAnalystV2

        agent = SocialMediaAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            tool_data={},
            state={"company_name": "Ping An Bank"},
        )

        assert "emotion research" in prompt
        assert "Noise source" in prompt
        assert "investment opportunities" not in prompt


class TestSectorAnalystV2:
    """Test sector analyst V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import SectorAnalystV2
        assert SectorAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import SectorAnalystV2

        assert SectorAnalystV2.metadata.id == "sector_analyst_v2"
        assert SectorAnalystV2.metadata.name == "Sector Analyst v2.0"
        assert SectorAnalystV2.analyst_type == "sector"
        assert SectorAnalystV2.output_field == "sector_report"

    def test_fallback_user_prompt_avoids_sector_allocation_language(self):
        """The test section analyst downgrade prompt word no longer requires configuration suggestions."""
        from core.agents.adapters import SectorAnalystV2

        agent = SectorAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            tool_data={},
            state={"company_name": "Ping An Bank", "market_type": "A shares"},
        )

        assert "Follow-up observations" in prompt
        assert "Industry growth opportunities and investment value" not in prompt
        assert "Industry Risks and Defense Strategies" not in prompt


class TestIndexAnalystV2:
    """Test market analysts V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import IndexAnalystV2
        assert IndexAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import IndexAnalystV2

        assert IndexAnalystV2.metadata.id == "index_analyst_v2"
        assert IndexAnalystV2.metadata.name == "Market Analyst v2.0"
        assert IndexAnalystV2.analyst_type == "index"
        assert IndexAnalystV2.output_field == "index_report"

    def test_fallback_user_prompt_avoids_macro_execution_language(self):
        """Testing market analyst downgrade prompts no longer requires target levels or allocation recommendations"""
        from core.agents.adapters import IndexAnalystV2

        agent = IndexAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            tool_data={},
            state={"company_name": "Ping An Bank", "market_type": "A shares"},
        )

        assert "Macro environment research" in prompt
        assert "Follow-up observations" in prompt
        assert "Rising opportunities and market hot spots" not in prompt
        assert "Downside Risk and Defensive Strategies" not in prompt


class TestBearResearcherV2:
    """Test Prudential Scenario Researcher V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import BearResearcherV2
        assert BearResearcherV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import BearResearcherV2

        assert BearResearcherV2.metadata.id == "bear_researcher_v2"
        assert BearResearcherV2.metadata.name == "Prudential Scenario Researcher v2.0"
        assert BearResearcherV2.researcher_type == "bear"
        assert BearResearcherV2.stance == "bear"


class TestRiskManagerV2:
    """Test Risk Assessor V2"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import RiskManagerV2
        assert RiskManagerV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import RiskManagerV2

        assert RiskManagerV2.metadata.id == "risk_manager_v2"
        assert RiskManagerV2.metadata.name == "risk assessor v2.0"
        assert RiskManagerV2.manager_type == "risk"
        assert RiskManagerV2.output_field == "risk_assessment"


# ==================== Position Analysis Agent Test ====================

class TestTechnicalAnalystV2:
    """Test technical analyst V2 (Position analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import TechnicalAnalystV2
        assert TechnicalAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import TechnicalAnalystV2

        assert TechnicalAnalystV2.metadata.id == "pa_technical_v2"
        assert TechnicalAnalystV2.metadata.name == "technical analyst v2.0"
        assert TechnicalAnalystV2.researcher_type == "position_technical"
        assert TechnicalAnalystV2.output_field == "technical_analysis"

    def test_fallback_user_prompt_avoids_execution_language(self):
        """The test downgrade prompt word is changed to the research judgment caliber"""
        from core.agents.adapters import TechnicalAnalystV2

        agent = TechnicalAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            reports={},
            historical_context=None,
            state={
                "position_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "cost_price": 10.0,
                    "current_price": 10.5,
                    "unrealized_pnl_pct": 5.0,
                },
                "market_data": {
                    "summary": "The trend is stable and the volume is average.",
                    "technical_indicators": "MACD Moving flat, RSI is neutral.",
                },
                "stock_analysis_report": {"has_cache": False},
            },
        )

        assert "Technical verification signal" in prompt
        assert "Operation suggestions" not in prompt
        assert "support resistance level" not in prompt


class TestFundamentalAnalystV2:
    """Test Fundamental Analyst V2 (Position analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import FundamentalAnalystV2
        assert FundamentalAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import FundamentalAnalystV2

        assert FundamentalAnalystV2.metadata.id == "pa_fundamental_v2"
        assert FundamentalAnalystV2.metadata.name == "fundamental analyst v2.0"
        assert FundamentalAnalystV2.researcher_type == "position_fundamental"
        assert FundamentalAnalystV2.output_field == "fundamental_analysis"

    def test_fallback_user_prompt_avoids_execution_language(self):
        """The test downgrade prompt word is changed to the research judgment caliber"""
        from core.agents.adapters import FundamentalAnalystV2

        agent = FundamentalAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            reports={},
            historical_context=None,
            state={
                "position_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "industry": "bank",
                    "cost_price": 10.0,
                    "current_price": 10.5,
                    "holding_days": 30,
                },
                "stock_analysis_report": {"has_cache": False},
            },
        )

        assert "public verification signal" in prompt
        assert "Fundamental operation suggestions based on positions" not in prompt
        assert "It is prohibited to output buying and selling advice" in prompt


class TestRiskAssessorV2:
    """Test Risk Assessor V2 (Position analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import RiskAssessorV2
        assert RiskAssessorV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import RiskAssessorV2

        assert RiskAssessorV2.metadata.id == "pa_risk_v2"
        assert RiskAssessorV2.metadata.name == "risk assessor v2.0"
        assert RiskAssessorV2.researcher_type == "position_risk"
        assert RiskAssessorV2.output_field == "risk_analysis"

    def test_fallback_user_prompt_avoids_reference_prices(self):
        """The test downgrade prompt word no longer requires a reference price"""
        from core.agents.adapters import RiskAssessorV2

        agent = RiskAssessorV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            reports={},
            historical_context=None,
            state={
                "position_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "quantity": 100,
                    "cost_price": 10.0,
                    "current_price": 10.5,
                    "market_value": 1050.0,
                    "unrealized_pnl": 50.0,
                    "unrealized_pnl_pct": 5.0,
                },
                "capital_info": {"total_assets": 100000.0},
                "market_data": {"volatility": "medium"},
                "stock_analysis_report": {"has_cache": False},
            },
        )

        assert "Follow-up observations" in prompt
        assert "Risk control reference price (for reference only)" not in prompt
        assert "Earnings expected reference price (for reference only)" not in prompt
        assert "It is prohibited to output the risk control reference price" in prompt


class TestActionAdvisorV2:
    """Test Position Research Integrator V2 (Position analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import ActionAdvisorV2
        assert ActionAdvisorV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import ActionAdvisorV2

        assert ActionAdvisorV2.metadata.id == "pa_advisor_v2"
        assert ActionAdvisorV2.metadata.name == "Position research integrator v2.0"
        assert ActionAdvisorV2.manager_type == "position_advisor"
        assert ActionAdvisorV2.output_field == "action_advice"

    def test_fallback_user_prompt_uses_research_schema(self):
        """Test degradation prompt word output research judgment format"""
        from core.agents.adapters import ActionAdvisorV2

        agent = ActionAdvisorV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            inputs={},
            debate_summary=None,
            state={
                "position_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "cost_price": 10.0,
                    "current_price": 10.5,
                    "unrealized_pnl_pct": 5.0,
                },
                "technical_analysis": "The trend is stable, and the coordination between volume and price is average.",
                "fundamental_analysis": "Profitability is stable and valuation is neutral.",
                "risk_analysis": "It is necessary to pay attention to changes in industry prosperity and asset quality.",
                "user_goal": {"target_return": 10, "stop_loss": -8},
            },
        )

        assert "Position research conclusion" in prompt
        assert "observation_factors" in prompt
        assert "price analysis range" not in prompt
        assert "Risk control reference price" not in prompt


# ==================== Review analysis agent test ====================

class TestTimingAnalystV2:
    """Test Timing Analyst V2 (Review analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import TimingAnalystV2
        assert TimingAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import TimingAnalystV2

        assert TimingAnalystV2.metadata.id == "timing_analyst_v2"
        assert TimingAnalystV2.metadata.name == "timing analyst v2.0"
        assert TimingAnalystV2.researcher_type == "review_timing"
        assert TimingAnalystV2.output_field == "timing_analysis"

    def test_fallback_user_prompt_avoids_execution_language(self):
        """The test timing review and downgrade prompts no longer require the optimal buying and selling point."""
        from core.agents.adapters import TimingAnalystV2

        agent = TimingAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            reports={},
            historical_context=None,
            state={
                "trade_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "holding_days": 12,
                    "realized_pnl": 120.0,
                    "realized_pnl_pct": 3.2,
                    "trades": [{"date": "2024-12-01", "side": "buy", "quantity": 100, "price": 10.2}],
                },
                "market_data": {"summary": "The market is volatile and the volume and energy are mediocre."},
            },
        )

        assert "Time to review" in prompt
        assert "Evidence integrity and disciplinary deviations" in prompt
        assert "The gap from the optimal point" not in prompt


class TestPositionAnalystV2:
    """Test Position Analyst V2 (Review analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import PositionAnalystV2
        assert PositionAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import PositionAnalystV2

        assert PositionAnalystV2.metadata.id == "position_analyst_v2"
        assert PositionAnalystV2.metadata.name == "Position Analyst v2.0"
        assert PositionAnalystV2.researcher_type == "review_position"
        assert PositionAnalystV2.output_field == "position_analysis"

    def test_fallback_user_prompt_avoids_future_position_plan(self):
        """The test position review and downgrade prompts no longer require the future increase or decrease of positions."""
        from core.agents.adapters import PositionAnalystV2

        agent = PositionAnalystV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            reports={},
            historical_context=None,
            state={
                "trade_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "realized_pnl": 120.0,
                    "realized_pnl_pct": 3.2,
                    "trades": [{"date": "2024-12-01", "side": "buy", "quantity": 100}],
                },
            },
        )

        assert "Position review" in prompt
        assert "Position change basis analysis" in prompt
        assert "Analysis of strategies for adding and subtracting positions" not in prompt


class TestEmotionAnalystV2:
    """Test Sentiment Analyst V2 (Review analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import EmotionAnalystV2
        assert EmotionAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import EmotionAnalystV2

        assert EmotionAnalystV2.metadata.id == "emotion_analyst_v2"
        assert EmotionAnalystV2.metadata.name == "sentiment analyst v2.0"
        assert EmotionAnalystV2.researcher_type == "review_emotion"
        assert EmotionAnalystV2.output_field == "emotion_analysis"


class TestAttributionAnalystV2:
    """Test Attribution Analyst V2 (Review analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import AttributionAnalystV2
        assert AttributionAnalystV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import AttributionAnalystV2

        assert AttributionAnalystV2.metadata.id == "attribution_analyst_v2"
        assert AttributionAnalystV2.metadata.name == "attribution analyst v2.0"
        assert AttributionAnalystV2.researcher_type == "review_attribution"
        assert AttributionAnalystV2.output_field == "attribution_analysis"


class TestReviewManagerV2:
    """Test Review Summarizer V2 (Review analysis)"""

    def test_import(self):
        """Test import"""
        from core.agents.adapters import ReviewManagerV2
        assert ReviewManagerV2 is not None

    def test_metadata(self):
        """Test metadata"""
        from core.agents.adapters import ReviewManagerV2

        assert ReviewManagerV2.metadata.id == "review_manager_v2"
        assert ReviewManagerV2.metadata.name == "Review summary expert v2.0"
        assert ReviewManagerV2.manager_type == "review_manager"
        assert ReviewManagerV2.output_field == "review_summary"

    def test_fallback_user_prompt_avoids_future_trade_actions(self):
        """Test review summary downgrade prompt words do not require future trading actions"""
        from core.agents.adapters import ReviewManagerV2

        agent = ReviewManagerV2()
        agent._get_prompt_from_template = lambda *args, **kwargs: None

        prompt = agent._build_user_prompt(
            ticker="000001",
            analysis_date="2024-12-15",
            inputs={},
            debate_summary=None,
            state={
                "trade_info": {
                    "code": "000001",
                    "name": "Ping An Bank",
                    "realized_pnl": 120.0,
                    "realized_pnl_pct": 3.2,
                    "holding_days": 12,
                },
                "timing_analysis": "The evidence for entry is basically sufficient, but the basis for exit is a bit hasty.",
                "position_analysis": "Position exposure basically matches the account size.",
                "emotion_analysis": "There was hesitation during the session due to short-term fluctuations.",
                "attribution_analysis": "The income mainly comes from the recovery of the industry and the improvement of individual stock fundamentals.",
            },
        )

        assert "It is forbidden to write suggestions as sales" in prompt
        assert "It should be executed at a certain price next time" in prompt


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

