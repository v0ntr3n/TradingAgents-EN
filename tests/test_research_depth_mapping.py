"""
Test whether the study depth mapping is correct
Verify conversion of front-end numeric grade to back-end Chinese grade
"""
import pytest
from app.services.simple_analysis_service import create_analysis_config


class TestResearchDepthMapping:
    """Testing Study Depth Mapping"""

    def test_level_1_fast(self):
        """Test Level 1 - Quick Analysis"""
        config = create_analysis_config(
            research_depth=1,  # Front-end incoming numbers 1
            selected_analysts=["market"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 1
        assert config["memory_enabled"] is False
        assert config["research_depth"] == "fast"

    def test_level_2_basic(self):
        """Test Level 2 - Basic Analysis"""
        config = create_analysis_config(
            research_depth=2,  # Front-end incoming numbers 2
            selected_analysts=["market"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 1
        assert config["memory_enabled"] is True
        assert config["research_depth"] == "Basics"

    def test_level_3_standard(self):
        """Test Level 3 - Standard Analysis"""
        config = create_analysis_config(
            research_depth=3,  # Front-end incoming numbers 3
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 2
        assert config["memory_enabled"] is True
        assert config["research_depth"] == "Standard"

    def test_level_4_deep(self):
        """Test Level 4 - In-Depth Analysis (critical test)"""
        config = create_analysis_config(
            research_depth=4,  # Front-end incoming numbers 4
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        # 🔥 Key assertion: Level 4 should have 2 rounds of debate
        assert config["max_debate_rounds"] == 2, "4 Level 1 in-depth analysis should have 2 rounds of debate"
        assert config["max_risk_discuss_rounds"] == 2, "4 Level 1 in-depth analysis should have 2 rounds of risk discussions"
        assert config["memory_enabled"] is True
        assert config["research_depth"] == "Depth"

    def test_level_5_comprehensive(self):
        """Test Level 5 - Full Analysis"""
        config = create_analysis_config(
            research_depth=5,  # Front-end incoming numbers 5
            selected_analysts=["market"],
            quick_model="qwen-max",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        # 🔥 Key assertion: Level 5 should have 3 rounds of debate
        assert config["max_debate_rounds"] == 3, "5 Level comprehensive analysis should have 3 rounds of debate"
        assert config["max_risk_discuss_rounds"] == 3, "5 A comprehensive analysis should have three rounds of risk discussions"
        assert config["memory_enabled"] is True
        assert config["research_depth"] == "Comprehensive"

    def test_chinese_depth_fast(self):
        """Test Chinese depth - fast"""
        config = create_analysis_config(
            research_depth="fast",  # Directly import Chinese
            selected_analysts=["market"],
            quick_model="qwen-turbo",
            deep_model="qwen-plus",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 1
        assert config["research_depth"] == "fast"

    def test_chinese_depth_deep(self):
        """Test Chinese Depth - Depth"""
        config = create_analysis_config(
            research_depth="Depth",  # Directly import Chinese
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 2
        assert config["max_risk_discuss_rounds"] == 2
        assert config["research_depth"] == "Depth"

    def test_chinese_depth_comprehensive(self):
        """Test Chinese Depth - Comprehensive"""
        config = create_analysis_config(
            research_depth="Comprehensive",  # Directly import Chinese
            selected_analysts=["market"],
            quick_model="qwen-max",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 3
        assert config["max_risk_discuss_rounds"] == 3
        assert config["research_depth"] == "Comprehensive"

    def test_string_number_depth(self):
        """Test string numeric depth"""
        config = create_analysis_config(
            research_depth="4",  # Number as string
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        assert config["max_debate_rounds"] == 2
        assert config["max_risk_discuss_rounds"] == 2
        assert config["research_depth"] == "Depth"

    def test_invalid_depth_fallback(self):
        """Test invalid depth and fall back to default value"""
        config = create_analysis_config(
            research_depth=99,  # Invalid number
            selected_analysts=["market"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        
        # Should fall back to standard analysis
        assert config["max_debate_rounds"] == 1
        assert config["max_risk_discuss_rounds"] == 2
        assert config["research_depth"] == "Standard"

    def test_debate_rounds_progression(self):
        """Testing the progression of debate rounds"""
        levels = [1, 2, 3, 4, 5]
        expected_debate_rounds = [1, 1, 1, 2, 3]
        expected_risk_rounds = [1, 1, 2, 2, 3]
        
        for level, expected_debate, expected_risk in zip(levels, expected_debate_rounds, expected_risk_rounds):
            config = create_analysis_config(
                research_depth=level,
                selected_analysts=["market"],
                quick_model="qwen-plus",
                deep_model="qwen-max",
                llm_provider="dashscope",
                market_type="A shares"
            )
            
            assert config["max_debate_rounds"] == expected_debate, \
                f"level{level}The debate round should be{expected_debate}, Actually{config['max_debate_rounds']}"
            assert config["max_risk_discuss_rounds"] == expected_risk, \
                f"level{level}The risk discussion round should be{expected_risk}, Actually{config['max_risk_discuss_rounds']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

