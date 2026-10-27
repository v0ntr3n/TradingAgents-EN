"""
Integration Testing: v2.0 Debate Workflow

Test the complete debate process:
1. Workflow layer initialization debate state
2. BullResearcherV2 Multiple rounds of debate with BearResearcherV2
3. ResearchManagerV2 Debate history comprehensively to make decisions
"""

import pytest
from unittest.mock import Mock, patch
from typing import Dict, Any

from core.agents.adapters.bull_researcher_v2 import BullResearcherV2
from core.agents.adapters.bear_researcher_v2 import BearResearcherV2
from core.agents.adapters.research_manager_v2 import ResearchManagerV2


@pytest.fixture
def mock_llm():
    """Mock LLM"""
    llm = Mock()
    
    # Simulate different responses
    responses = [
        "Optimistic view: Based on strong financial reports, the company s performance is attractive for research",
        "Prudent view: However, valuations are too high and there is a risk of a correction",
        "Optimistic rebuttal: High valuations reflect market expectations for future growth",
        "Prudent rebuttal: market expectations are too optimistic and risks are underestimated",
        "Comprehensive research observation: The current tendency is to be cautious and need to be followed up",
    ]
    
    llm.invoke = Mock(side_effect=[Mock(content=r) for r in responses])
    
    return llm


@pytest.fixture
def initial_state():
    """Initial state (simulating the state after initialization of the workflow layer)"""
    return {
        "ticker": "AAPL",
        "analysis_date": "2024-01-15",
        "market_report": "The overall market is improving, with technology stocks performing strongly",
        "news_report": "Apple releases new products, market response is positive",
        "fundamentals_report": "Revenue increased by 20%, profit margin increased",
        # Debate status of workflow layer initialization
        "investment_debate_state": {
            "history": "",
            "bull_history": "",
            "bear_history": "",
            "current_response": "",
            "judge_decision": "",
            "count": 0,
        }
    }


class TestDebateWorkflowIntegration:
    """Test Debate Workflow Integration"""
    
    def test_two_round_debate(self, mock_llm, initial_state):
        """Test the two-round debate process"""
        
        # Create Agent instance
        bull_agent = BullResearcherV2(llm=mock_llm)
        bear_agent = BearResearcherV2(llm=mock_llm)
        manager_agent = ResearchManagerV2(llm=mock_llm)
        
        state = initial_state.copy()
        
        # Round 1: Optimistic Scenario Researcher Speaks
        result1 = bull_agent.execute(state)
        state.update(result1)
        
        # Verify Debate Status Update
        assert "investment_debate_state" in state
        debate_state = state["investment_debate_state"]
        assert "Bull Analyst:" in debate_state["history"]
        assert "optimistic view" in debate_state["bull_history"]
        
        # Round 1: Prudential Scenario Fellows Speak
        result2 = bear_agent.execute(state)
        state.update(result2)
        
        # Verify Debate Status Update
        debate_state = state["investment_debate_state"]
        assert "Bear Analyst:" in debate_state["history"]
        assert "Prudent view" in debate_state["bear_history"]
        
        # Round 2: Optimistic Scenario Researcher Rebuttal
        result3 = bull_agent.execute(state)
        state.update(result3)
        
        # Verify debate history accumulation
        debate_state = state["investment_debate_state"]
        assert debate_state["history"].count("Bull Analyst:") == 2
        
        # Round 2: Prudential Scenario Researcher Rebuttal
        result4 = bear_agent.execute(state)
        state.update(result4)
        
        # Verify debate history accumulation
        debate_state = state["investment_debate_state"]
        assert debate_state["history"].count("Bear Analyst:") == 2
        
        # Research Manager Summary
        result5 = manager_agent.execute(state)
        state.update(result5)
        
        # Validate final decision
        assert "investment_plan" in state
        assert "judge_decision" in state["investment_debate_state"]
        assert "Comprehensive research observations" in state["investment_debate_state"]["judge_decision"]
    
    def test_debate_context_propagation(self, mock_llm, initial_state):
        """Test debate context passed across multiple rounds"""
        
        bull_agent = BullResearcherV2(llm=mock_llm)
        bear_agent = BearResearcherV2(llm=mock_llm)
        
        state = initial_state.copy()
        
        # Round 1
        result1 = bull_agent.execute(state)
        state.update(result1)
        
        # Round 2: The cautious scenario researcher should be able to see the optimistic scenario researcher's perspective
        with patch.object(bear_agent, '_get_debate_context') as mock_get_context:
            mock_get_context.return_value = "Mock context"
            
            result2 = bear_agent.execute(state)
            
            # Verification is called _get_debate_context
            mock_get_context.assert_called_once()
            
            # Verify that the incoming state contains debate history
            call_args = mock_get_context.call_args[0][0]
            assert "investment_debate_state" in call_args
            assert "Bull Analyst:" in call_args["investment_debate_state"]["history"]
    
    def test_single_analysis_mode_fallback(self, mock_llm):
        """Test single analysis mode (no debate state)"""
        
        bull_agent = BullResearcherV2(llm=mock_llm)
        
        # There is no state for investment_debate_state
        state = {
            "ticker": "AAPL",
            "analysis_date": "2024-01-15",
            "market_report": "market report",
        }
        
        result = bull_agent.execute(state)
        
        # The report should be returned but does not contain investment_debate_state
        assert "bull_report" in result
        assert "investment_debate_state" not in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

