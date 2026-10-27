"""
Test whether ConditionalLogic receives configuration parameters correctly
Verify that the debate round configuration is correctly passed to TradingAgentsGraph
"""
import pytest
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG


class TestConditionalLogicConfig:
    """Test ConditionalLogic configuration pass"""

    def test_conditional_logic_default_params(self):
        """Test ConditionalLogic default parameters"""
        logic = ConditionalLogic()
        
        assert logic.max_debate_rounds == 1
        assert logic.max_risk_discuss_rounds == 1

    def test_conditional_logic_custom_params(self):
        """Test ConditionalLogic custom parameters"""
        logic = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=2)
        
        assert logic.max_debate_rounds == 3
        assert logic.max_risk_discuss_rounds == 2

    def test_trading_graph_with_level_4_config(self):
        """Testing TradingGraph using level 4 depth configuration"""
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = 2
        config["max_risk_discuss_rounds"] = 2
        config["research_depth"] = "Depth"
        
        graph = TradingAgentsGraph(
            selected_analysts=["market"],
            config=config
        )
        
        # 🔥 Key assertion: ConditionalLogic should receive the correct configuration
        assert graph.conditional_logic.max_debate_rounds == 2, \
            f"4 There should be 2 rounds of debate for level 1 in-depth analysis, but actually it is{graph.conditional_logic.max_debate_rounds}"
        assert graph.conditional_logic.max_risk_discuss_rounds == 2, \
            f"4 There should be 2 rounds of risk discussions for level 1 in-depth analysis. In fact, it is{graph.conditional_logic.max_risk_discuss_rounds}"

    def test_trading_graph_with_level_5_config(self):
        """Testing TradingGraph using 5-level depth configuration"""
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = 3
        config["max_risk_discuss_rounds"] = 3
        config["research_depth"] = "Comprehensive"
        
        graph = TradingAgentsGraph(
            selected_analysts=["market"],
            config=config
        )
        
        # 🔥 Key assertion: ConditionalLogic should receive the correct configuration
        assert graph.conditional_logic.max_debate_rounds == 3, \
            f"5 There should be three rounds of debates for a comprehensive analysis at the level of{graph.conditional_logic.max_debate_rounds}"
        assert graph.conditional_logic.max_risk_discuss_rounds == 3, \
            f"5 A level comprehensive analysis should have three rounds of risk discussions, but the actual{graph.conditional_logic.max_risk_discuss_rounds}"

    def test_trading_graph_without_config(self):
        """Use default values when testing TradingGraph without passing configuration"""
        graph = TradingAgentsGraph(selected_analysts=["market"])
        
        # Default configuration should be used
        assert graph.conditional_logic.max_debate_rounds == 1
        assert graph.conditional_logic.max_risk_discuss_rounds == 1

    def test_trading_graph_with_partial_config(self):
        """Test TradingGraph partial configuration"""
        config = DEFAULT_CONFIG.copy()
        config["max_debate_rounds"] = 5  # Only set debate rounds
        
        graph = TradingAgentsGraph(
            selected_analysts=["market"],
            config=config
        )
        
        assert graph.conditional_logic.max_debate_rounds == 5
        assert graph.conditional_logic.max_risk_discuss_rounds == 1  # Use default value


class TestDebateRoundsProgression:
    """Testing the progression of debate rounds"""

    @pytest.mark.parametrize("level,debate_rounds,risk_rounds", [
        (1, 1, 1),  # fast
        (2, 1, 1),  # Basics
        (3, 1, 2),  # Standard
        (4, 2, 2),  # Depth
        (5, 3, 3),  # Comprehensive
    ])
    def test_debate_rounds_by_level(self, level, debate_rounds, risk_rounds):
        """Test different levels of debate rounds"""
        from app.services.simple_analysis_service import create_analysis_config
        
        config_dict = create_analysis_config(
            research_depth=level,
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        # Create TradingGraph and verify configuration passed
        graph = TradingAgentsGraph(
            selected_analysts=["market"],
            config=config_dict
        )
        
        assert graph.conditional_logic.max_debate_rounds == debate_rounds, \
            f"level{level}The debate round should be{debate_rounds}, Actually{graph.conditional_logic.max_debate_rounds}"
        assert graph.conditional_logic.max_risk_discuss_rounds == risk_rounds, \
            f"level{level}The risk discussion round should be{risk_rounds}, Actually{graph.conditional_logic.max_risk_discuss_rounds}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

