"""
Test configurations at 5 research depth levels
"""
import pytest
from app.services.simple_analysis_service import create_analysis_config


class TestResearchDepth5Levels:
    """Test 5 research depth levels"""

    def test_depth_level_1_fast(self):
        """Test Level 1 - Quick Analysis"""
        config = create_analysis_config(
            research_depth="fast",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 1
        assert config["memory_enabled"] is False  # Quick analysis of disabled memories
        assert config["online_tools"] is False  # Quick analysis of disabled online tools
        assert config["quick_think_llm"] == "qwen-turbo"
        assert config["deep_think_llm"] == "qwen-plus"

    def test_depth_level_2_basic(self):
        """Test Level 2 - Basic Analysis"""
        config = create_analysis_config(
            research_depth="Basics",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 1
        assert config["memory_enabled"] is True
        assert config["online_tools"] is True
        assert config["quick_think_llm"] == "qwen-turbo"
        assert config["deep_think_llm"] == "qwen-plus"

    def test_depth_level_3_standard(self):
        """Test Level 3 - Standard Analysis (recommended)"""
        config = create_analysis_config(
            research_depth="Standard",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 2  # Standard analysis adds risk discussion
        assert config["memory_enabled"] is True
        assert config["online_tools"] is True
        assert config["quick_think_llm"] == "qwen-plus"
        assert config["deep_think_llm"] == "qwen-max"

    def test_depth_level_4_deep(self):
        """Test Level 4 - In-Depth Analysis"""
        config = create_analysis_config(
            research_depth="Depth",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 2  # In-depth analysis increases debate rounds
        assert config["max_risk_discuss_rounds"] == 2
        assert config["memory_enabled"] is True
        assert config["online_tools"] is True
        assert config["quick_think_llm"] == "qwen-plus"
        assert config["deep_think_llm"] == "qwen-max"

    def test_depth_level_5_comprehensive(self):
        """Test Level 5 - Full Analysis"""
        config = create_analysis_config(
            research_depth="Comprehensive",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-max",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 3  # Comprehensive analysis of the most debate rounds
        assert config["max_risk_discuss_rounds"] == 3  # Comprehensive analysis of the most risky discussions
        assert config["memory_enabled"] is True
        assert config["online_tools"] is True
        assert config["quick_think_llm"] == "qwen-max"
        assert config["deep_think_llm"] == "qwen-max"

    def test_unknown_depth_defaults_to_standard(self):
        """Testing for unknown depths uses standard analysis by default"""
        config = create_analysis_config(
            research_depth="unknown level",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        # Standard analysis configuration should be used
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 2
        assert config["memory_enabled"] is True
        assert config["online_tools"] is True

    def test_all_depths_have_correct_progression(self):
        """Test progression relationships at all depth levels"""
        depths = ["fast", "Basics", "Standard", "Depth", "Comprehensive"]
        configs = []

        for depth in depths:
            config = create_analysis_config(
                research_depth=depth,
                selected_analysts=["market", "fundamentals"],
                quick_model="qwen-plus",
                deep_model="qwen-max",
                llm_provider="dashscope",
                market_type="A shares"
            )
            configs.append({
                "depth": depth,
                "debate_rounds": config["max_debate_rounds"],
                "risk_rounds": config["max_risk_discuss_rounds"],
                "memory": config["memory_enabled"],
                "online": config["online_tools"]
            })

        # Verification debate rounds are increased (except for the first 3 levels, which are all 1 round)
        assert configs[0]["debate_rounds"] == 1  # fast
        assert configs[1]["debate_rounds"] == 1  # Basics
        assert configs[2]["debate_rounds"] == 1  # Standard
        assert configs[3]["debate_rounds"] == 2  # Depth
        assert configs[4]["debate_rounds"] == 3  # Comprehensive

        # Validation risk discussion round
        assert configs[0]["risk_rounds"] == 1  # fast
        assert configs[1]["risk_rounds"] == 1  # Basics
        assert configs[2]["risk_rounds"] == 2  # Standard
        assert configs[3]["risk_rounds"] == 2  # Depth
        assert configs[4]["risk_rounds"] == 3  # Comprehensive

        # Validation memory and online tools (quick analysis disabled, others enabled)
        assert configs[0]["memory"] is False  # fast
        assert configs[0]["online"] is False  # fast
        for i in range(1, 5):
            assert configs[i]["memory"] is True
            assert configs[i]["online"] is True


class TestDepthReasoningEffortMapping:
    """Test research depth level → reasoning_effort Thinking About Budget Mapping (A1)"""

    def test_five_depths_map_to_efforts(self):
        """The fifth depth level should be mapped to the Volcano Ark reasoning_effort level"""
        expected = {
            "fast": "minimal",
            "Basics": "low",
            "Standard": "medium",
            "Depth": "high",
            "Comprehensive": "xhigh",
        }
        for depth, effort in expected.items():
            config = create_analysis_config(
                research_depth=depth,
                selected_analysts=["market", "fundamentals"],
                quick_model="qwen-plus",
                deep_model="qwen-max",
                llm_provider="dashscope",
                market_type="A shares"
            )
            assert config["depth_reasoning_effort"] == effort, f"{depth} should be mapped to {effort}"

    def test_numeric_depth_maps_effort(self):
        """Digital gears (1-5) are also mapped"""
        expected = {1: "minimal", 2: "low", 3: "medium", 4: "high", 5: "xhigh"}
        for level, effort in expected.items():
            config = create_analysis_config(
                research_depth=level,
                selected_analysts=["market", "fundamentals"],
                quick_model="qwen-plus",
                deep_model="qwen-max",
                llm_provider="dashscope",
                market_type="A shares"
            )
            assert config["depth_reasoning_effort"] == effort

    def test_unknown_depth_defaults_effort_medium(self):
        """Unknown depth scale effort falls back to medium"""
        config = create_analysis_config(
            research_depth="Non-existent gear",
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        assert config["depth_reasoning_effort"] == "medium"


class TestAnalysisParametersDefault:
    """Default values for test analysis parameters"""

    def test_default_research_depth_is_standard(self):
        """The default research depth for testing is'Standard'"""
        from app.models.analysis import AnalysisParameters
        
        params = AnalysisParameters()
        assert params.research_depth == "Standard"

    def test_research_depth_accepts_all_5_levels(self):
        """Test Study Depth accepts all 5 levels"""
        from app.models.analysis import AnalysisParameters
        
        valid_depths = ["fast", "Basics", "Standard", "Depth", "Comprehensive"]
        
        for depth in valid_depths:
            params = AnalysisParameters(research_depth=depth)
            assert params.research_depth == depth


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

