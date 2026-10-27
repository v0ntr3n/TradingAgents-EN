"""
Testing ResearcherAgent s debate mode functionality

Test content:
1. Debate pattern detection
2. Debate context building
3. Debate status update
4. Single analysis mode (backwards compatible)
"""

import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, Any

from core.agents.researcher import ResearcherAgent


class MockResearcherAgent(ResearcherAgent):
    """for testing Mock ResearcherAgent"""
    
    researcher_type = "test"
    output_field = "test_report"
    stance = "bull"
    debate_state_field = "investment_debate_state"
    history_field = "bull_history"
    opponent_history_field = "bear_history"
    
    def _build_system_prompt(self, stance: str, state: Dict[str, Any] = None) -> str:
        return "Test system prompt"
    
    def _build_user_prompt(
        self,
        ticker: str,
        analysis_date: str,
        reports: Dict[str, Any],
        historical_context: str,
        state: Dict[str, Any]
    ) -> str:
        return f"Test user prompt with context: {historical_context}"
    
    def _get_required_reports(self):
        return ["market_report"]


class TestDebateModeDetection:
    """Test Debate Mode Detection"""
    
    def test_is_debate_mode_true(self):
        """Test detects debate mode"""
        agent = MockResearcherAgent()
        
        state = {
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "bear_history": "",
                "count": 0,
            }
        }
        
        assert agent._is_debate_mode(state) is True
    
    def test_is_debate_mode_false_no_field(self):
        """Test has no debate status field"""
        agent = MockResearcherAgent()
        
        state = {
            "ticker": "AAPL",
            "analysis_date": "2024-01-15",
        }
        
        assert agent._is_debate_mode(state) is False
    
    def test_is_debate_mode_false_not_dict(self):
        """Test debate status field is not a dictionary"""
        agent = MockResearcherAgent()
        
        state = {
            "investment_debate_state": "not a dict"
        }
        
        assert agent._is_debate_mode(state) is False


class TestDebateContextBuilding:
    """Test debate context building"""
    
    def test_get_debate_context_with_history(self):
        """Test to get debate context (with history)"""
        agent = MockResearcherAgent()
        
        state = {
            "investment_debate_state": {
                "history": "Bull: optimistic\nBear: Prudence",
                "bull_history": "Bull: optimistic",
                "bear_history": "Bear: Prudence",
                "current_response": "Bear: Prudence",
            }
        }
        
        context = agent._get_debate_context(state)
        
        assert " [Full debate history]" in context
        assert "Bull: optimistic" in context
        assert "Bear: Prudence" in context
        assert " [The other party s latest views]" in context
    
    def test_get_debate_context_empty(self):
        """Test getting debate context (empty history)"""
        agent = MockResearcherAgent()
        
        state = {
            "investment_debate_state": {
                "history": "",
                "current_response": "",
            }
        }
        
        context = agent._get_debate_context(state)
        
        assert context == ""
    
    def test_get_debate_context_with_opponent_history(self):
        """Test to obtain the other party s history"""
        agent = MockResearcherAgent()
        agent.opponent_history_field = "bear_history"
        
        state = {
            "investment_debate_state": {
                "history": "Bull: optimistic\nBear: Prudence",
                "bear_history": "Bear: Prudence",
                "current_response": "Bear: Prudence",
            }
        }
        
        context = agent._get_debate_context(state)
        
        # The opponent's history should be included in the context (if different from the full history)
        assert "Bear: Prudence" in context


class TestDebateStateUpdate:
    """Test debate status update"""
    
    def test_update_debate_state_basic(self):
        """Testing basic debate status updates"""
        agent = MockResearcherAgent()
        
        state = {
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "bear_history": "",
                "count": 0,
            }
        }
        
        response = {"content": "I think the current research conclusions tend to be optimistic"}
        result = {}
        
        updated_result = agent._update_debate_state(state, response, result)
        
        assert "investment_debate_state" in updated_result
        debate_state = updated_result["investment_debate_state"]
        
        assert "Bull Analyst: I think the current research conclusions tend to be optimistic" in debate_state["history"]
        assert "Bull Analyst: I think the current research conclusions tend to be optimistic" in debate_state["bull_history"]
        assert debate_state["current_response"] == "Bull Analyst: I think the current research conclusions tend to be optimistic"

    def test_update_debate_state_preserves_count(self):
        """Keep count when testing update debate status (managed by workflow layer)"""
        agent = MockResearcherAgent()

        state = {
            "investment_debate_state": {
                "history": "Previous history",
                "bull_history": "",
                "bear_history": "",
                "count": 5,  # Existing count
            }
        }

        response = "new perspective"
        result = {}

        updated_result = agent._update_debate_state(state, response, result)
        debate_state = updated_result["investment_debate_state"]

        # count should be retained and should not be modified
        assert debate_state["count"] == 5

    def test_update_debate_state_with_string_response(self):
        """test string response"""
        agent = MockResearcherAgent()

        state = {
            "investment_debate_state": {
                "history": "",
                "bull_history": "",
                "count": 0,
            }
        }

        response = "Direct string response"
        result = {}

        updated_result = agent._update_debate_state(state, response, result)
        debate_state = updated_result["investment_debate_state"]

        assert "Bull Analyst: Direct string response" in debate_state["history"]


class TestSpeakerLabel:
    """Test speaker label"""

    def test_get_speaker_label_bull(self):
        """Testing Optimistic Scenarios Researcher Tags"""
        agent = MockResearcherAgent()
        agent.stance = "bull"

        assert agent._get_speaker_label() == "Bull Analyst"

    def test_get_speaker_label_bear(self):
        """Test Prudence Scenario Researcher Tags"""
        agent = MockResearcherAgent()
        agent.stance = "bear"

        assert agent._get_speaker_label() == "Bear Analyst"

    def test_get_speaker_label_risky(self):
        """Test Risk Researcher Tags"""
        agent = MockResearcherAgent()
        agent.stance = "risky"

        assert agent._get_speaker_label() == "Risky Analyst"

    def test_get_speaker_label_unknown(self):
        """Test unknown positions"""
        agent = MockResearcherAgent()
        agent.stance = "unknown"

        assert agent._get_speaker_label() == "Analyst"


class TestBackwardCompatibility:
    """Testing for backward compatibility (single analysis mode)"""

    def test_single_analysis_mode(self):
        """Test single analysis mode (no debate state)"""
        agent = MockResearcherAgent()

        # Mock LLM
        agent._llm = Mock()
        agent._llm.invoke = Mock(return_value=Mock(content="Analyze results"))

        state = {
            "ticker": "AAPL",
            "analysis_date": "2024-01-15",
            "market_report": "market report",
        }

        result = agent.execute(state)

        # The report should be returned but does not contain investment_debate_state
        assert "test_report" in result
        assert "investment_debate_state" not in result

    def test_memory_context_in_single_mode(self):
        """Test single analysis mode using Memory context"""
        agent = MockResearcherAgent()

        # Mock Memory
        agent.memory = Mock()
        agent.memory.search_memories = Mock(return_value=[
            {"content": "historical advice 1", "similarity": 0.91},
            {"content": "historical advice 2", "similarity": 0.89},
        ])

        reports = {"market_report": "Current market report"}
        context = agent._get_memory_context("AAPL", reports)

        assert " [Historical experience]" in context
        assert "historical advice 1" in context
        assert "historical advice 2" in context

    def test_memory_context_no_memory(self):
        """Tested without Memory system"""
        agent = MockResearcherAgent()
        agent.memory = None

        reports = {"market_report": "Current market report"}
        context = agent._get_memory_context("AAPL", reports)

        assert context == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


