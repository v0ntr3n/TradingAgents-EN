"""
Test debate process simulation
Verify whether round control of investment debates and risk discussions is correct
"""
import pytest
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.agents.utils.agent_states import AgentState, InvestDebateState, RiskDebateState


class TestInvestmentDebateFlow:
    """Testing the Investment Debate Process"""

    def test_level_4_investment_debate_2_rounds(self):
        """Investment debate testing level 4 in-depth analysis (2 rounds)"""
        logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)
        
        # mock investment debate status
        state = {
            "investment_debate_state": {
                "count": 0,
                "current_response": "Bull Researcher"
            }
        }
        
        # Round 1
        # Bull -> Bear
        assert logic.should_continue_debate(state) == "Bear Researcher"
        state["investment_debate_state"]["count"] = 1
        state["investment_debate_state"]["current_response"] = "Bear Researcher"  # updated to Bear

        # Bear -> Bull
        assert logic.should_continue_debate(state) == "Bull Researcher"
        state["investment_debate_state"]["count"] = 2
        state["investment_debate_state"]["current_response"] = "Bull Researcher"  # updated to Bull

        # Round 2
        # Bull -> Bear
        assert logic.should_continue_debate(state) == "Bear Researcher"
        state["investment_debate_state"]["count"] = 3
        state["investment_debate_state"]["current_response"] = "Bear Researcher"  # updated to Bear

        # Bear -> Research Manager (end)
        # count = 4 >= 2 * 2 = 4
        state["investment_debate_state"]["count"] = 4
        assert logic.should_continue_debate(state) == "Research Manager"

    def test_level_5_investment_debate_3_rounds(self):
        """Test Level 5 comprehensively analyzed investment debate (3 rounds)"""
        logic = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=3)
        
        state = {
            "investment_debate_state": {
                "count": 0,
                "current_response": "Bull Researcher"
            }
        }
        
        # Round 1:Bull -> Bear -> Bull
        for i in range(2):
            assert logic.should_continue_debate(state) in ["Bear Researcher", "Bull Researcher"]
            state["investment_debate_state"]["count"] = i + 1
        
        # Round 2:Bear -> Bull -> Bear
        for i in range(2, 4):
            assert logic.should_continue_debate(state) in ["Bear Researcher", "Bull Researcher"]
            state["investment_debate_state"]["count"] = i + 1
        
        # Round 3:Bull -> Bear
        for i in range(4, 6):
            assert logic.should_continue_debate(state) in ["Bear Researcher", "Bull Researcher"]
            state["investment_debate_state"]["count"] = i + 1
        
        # count = 6 >= 2 * 3 = 6, end
        assert logic.should_continue_debate(state) == "Research Manager"


class TestRiskDebateFlow:
    """Test risk discussion process"""

    def test_level_4_risk_debate_2_rounds(self):
        """Test risk discussion for level 4 in-depth analysis (2 rounds)"""
        logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)
        
        # mock risk debate status
        state = {
            "risk_debate_state": {
                "count": 0,
                "latest_speaker": "Risky Analyst"
            }
        }
        
        # Round 1:Risky -> Safe -> Neutral
        # Risky -> Safe
        assert logic.should_continue_risk_analysis(state) == "Safe Analyst"
        state["risk_debate_state"]["count"] = 1
        state["risk_debate_state"]["latest_speaker"] = "Safe Analyst"  # updated to Safe

        # Safe -> Neutral
        assert logic.should_continue_risk_analysis(state) == "Neutral Analyst"
        state["risk_debate_state"]["count"] = 2
        state["risk_debate_state"]["latest_speaker"] = "Neutral Analyst"  # updated to Neutral

        # Neutral -> Risky
        assert logic.should_continue_risk_analysis(state) == "Risky Analyst"
        state["risk_debate_state"]["count"] = 3
        state["risk_debate_state"]["latest_speaker"] = "Risky Analyst"  # updated to Risky

        # Round 2:Risky -> Safe -> Neutral
        # Risky -> Safe
        assert logic.should_continue_risk_analysis(state) == "Safe Analyst"
        state["risk_debate_state"]["count"] = 4
        state["risk_debate_state"]["latest_speaker"] = "Safe Analyst"  # updated to Safe

        # Safe -> Neutral
        assert logic.should_continue_risk_analysis(state) == "Neutral Analyst"
        state["risk_debate_state"]["count"] = 5
        state["risk_debate_state"]["latest_speaker"] = "Neutral Analyst"  # updated to Neutral

        # Neutral -> Risk Judge (end)
        # count = 6 >= 3 * 2 = 6
        state["risk_debate_state"]["count"] = 6
        assert logic.should_continue_risk_analysis(state) == "Risk Judge"

    def test_level_5_risk_debate_3_rounds(self):
        """Test Level 5 Full Analysis Risk Discussion (3 rounds)"""
        logic = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=3)
        
        state = {
            "risk_debate_state": {
                "count": 0,
                "latest_speaker": "Risky Analyst"
            }
        }
        
        speakers = ["Risky Analyst", "Safe Analyst", "Neutral Analyst"]
        expected_next = ["Safe Analyst", "Neutral Analyst", "Risky Analyst"]
        
        # 3 Rounds, 3 speakers per round
        for round_num in range(3):
            for speaker_idx in range(3):
                current_count = round_num * 3 + speaker_idx
                state["risk_debate_state"]["count"] = current_count
                state["risk_debate_state"]["latest_speaker"] = speakers[speaker_idx]
                
                if current_count < 9:  # 3 * 3 = 9
                    next_speaker = logic.should_continue_risk_analysis(state)
                    assert next_speaker == expected_next[speaker_idx], \
                        f"rounds{round_num+1}, speaker{speaker_idx+1}, Hope the next one is{expected_next[speaker_idx]}, Actually{next_speaker}"
        
        # count = 9 >= 3 * 3 = 9, end
        state["risk_debate_state"]["count"] = 9
        assert logic.should_continue_risk_analysis(state) == "Risk Judge"


class TestDebateRoundsCalculation:
    """Test debate round calculation"""

    @pytest.mark.parametrize("max_debate_rounds,expected_total_count", [
        (1, 2),   # 1 wheel = 2 speeches (Bull + Bear) 
        (2, 4),   # 2 wheel = 4 speeches
        (3, 6),   # 3 wheel = 6 speeches
        (5, 10),  # 5 wheel = 10 speeches
    ])
    def test_investment_debate_total_count(self, max_debate_rounds, expected_total_count):
        """Total number of speeches in the test investment debate"""
        logic = ConditionalLogic(max_debate_rounds=max_debate_rounds)
        
        state = {
            "investment_debate_state": {
                "count": expected_total_count - 1,
                "current_response": "Bull Researcher"
            }
        }
        
        # Threshold not reached, debate continues
        assert logic.should_continue_debate(state) in ["Bear Researcher", "Bull Researcher"]
        
        # Threshold reached, end of debate
        state["investment_debate_state"]["count"] = expected_total_count
        assert logic.should_continue_debate(state) == "Research Manager"

    @pytest.mark.parametrize("max_risk_discuss_rounds,expected_total_count", [
        (1, 3),   # 1 wheel = 3 speeches (Risky + Safe + Neutral) 
        (2, 6),   # 2 wheel = 6 speeches
        (3, 9),   # 3 wheel = 9 speeches
        (5, 15),  # 5 wheel = 15 speeches
    ])
    def test_risk_debate_total_count(self, max_risk_discuss_rounds, expected_total_count):
        """Total number of times the test risk discussion was spoken"""
        logic = ConditionalLogic(max_risk_discuss_rounds=max_risk_discuss_rounds)
        
        state = {
            "risk_debate_state": {
                "count": expected_total_count - 1,
                "latest_speaker": "Risky Analyst"
            }
        }
        
        # The threshold has not been reached, continue the discussion
        assert logic.should_continue_risk_analysis(state) in ["Safe Analyst", "Neutral Analyst", "Risky Analyst"]
        
        # Threshold reached, end discussion
        state["risk_debate_state"]["count"] = expected_total_count
        assert logic.should_continue_risk_analysis(state) == "Risk Judge"


class TestDebateFlowSummary:
    """Summary of test debate process"""

    def test_level_4_complete_flow(self):
        """Test the complete process of level 4 in-depth analysis"""
        logic = ConditionalLogic(max_debate_rounds=2, max_risk_discuss_rounds=2)
        
        # Investment Debate: Round 2 = 4 speeches
        # Risk discussion: 2 rounds = 6 speeches
        
        print("\n4 Level in-depth analysis process:")
        print("Investment Debate (2 rounds):")
        print("  Round 1:Bull -> Bear")
        print("  Round 2:Bull -> Bear")
        print("  Total: 4 speeches")
        
        print("\n Risk Discussion (2 rounds):")
        print("  Round 1:Risky -> Safe -> Neutral")
        print("  Round 2:Risky -> Safe -> Neutral")
        print("  Total: 6 speeches")
        
        assert logic.max_debate_rounds == 2
        assert logic.max_risk_discuss_rounds == 2

    def test_level_5_complete_flow(self):
        """Test the complete process of level 5 comprehensive analysis"""
        logic = ConditionalLogic(max_debate_rounds=3, max_risk_discuss_rounds=3)
        
        # Investment Debate: 3 rounds = 6 speeches
        # Risk Discussion: 3 rounds = 9 speeches
        
        print("\n5 Comprehensive analysis process:")
        print("Investment Debate (3 rounds):")
        print("  Round 1:Bull -> Bear")
        print("  Round 2:Bull -> Bear")
        print("  Round 3:Bull -> Bear")
        print("  Total: 6 speeches")
        
        print("\n Risk Discussion (3 rounds):")
        print("  Round 1:Risky -> Safe -> Neutral")
        print("  Round 2:Risky -> Safe -> Neutral")
        print("  Round 3:Risky -> Safe -> Neutral")
        print("  Total: 9 speeches")
        
        assert logic.max_debate_rounds == 3
        assert logic.max_risk_discuss_rounds == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

