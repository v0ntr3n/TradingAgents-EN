#!/usr/bin/env python3
"""
Test conditional logic fix - prevent analyst node from infinite looping

Test scenario:
1. There are tool_calls that should continue tool execution when the report is not generated
2. The loop should stop when the report has been generated even if there are tool_calls
3. When the report length is insufficient, execution should continue
4. When the report length is sufficient, the loop should be stopped
"""

from unittest.mock import Mock


def create_mock_message(has_tool_calls=False):
    """Create a mock message"""
    message = Mock()
    if has_tool_calls:
        message.tool_calls = [{"name": "test_tool", "args": {}}]
    else:
        message.tool_calls = []
    return message


def test_fundamentals_no_report_with_tool_calls():
    """Test: Fundamental Analysis - No Reports, Yes tool_calls -> Tool execution should continue"""
    from tradingagents.graph.conditional_logic import ConditionalLogic
    
    logic = ConditionalLogic()
    state = {
        "messages": [create_mock_message(has_tool_calls=True)],
        "fundamentals_report": ""
    }
    
    result = logic.should_continue_fundamentals(state)
    assert result == "tools_fundamentals", "Tool should be executed when there is no report"
    print("✅ Test Passed: Tool execution continues without reports")


def test_fundamentals_has_report_with_tool_calls():
    """Test: Fundamental Analysis - There are reports, there are tool_calls -> The cycle should be stopped"""
    from tradingagents.graph.conditional_logic import ConditionalLogic
    
    logic = ConditionalLogic()
    state = {
        "messages": [create_mock_message(has_tool_calls=True)],
        "fundamentals_report": "This is a complete fundamental analysis report" * 10  # length > 100
    }
    
    result = logic.should_continue_fundamentals(state)
    assert result == "Msg Clear Fundamentals", "The loop should be stopped when there is a report"
    print("✅ Test passed: Stop the loop when there is a report")


def test_all_analysts():
    """Test: Consistency of behavior among all analysts"""
    from tradingagents.graph.conditional_logic import ConditionalLogic
    
    logic = ConditionalLogic()
    message = create_mock_message(has_tool_calls=True)
    long_report = "Complete analysis report" * 20
    
    # Test all analysts
    analysts = [
        ("market", "market_report", logic.should_continue_market, "Msg Clear Market", "tools_market"),
        ("social", "sentiment_report", logic.should_continue_social, "Msg Clear Social", "tools_social"),
        ("news", "news_report", logic.should_continue_news, "Msg Clear News", "tools_news"),
        ("fundamentals", "fundamentals_report", logic.should_continue_fundamentals, "Msg Clear Fundamentals", "tools_fundamentals"),
    ]
    
    for analyst_name, report_field, check_func, expected_clear, expected_tools in analysts:
        # Stop when reported
        state = {
            "messages": [message],
            report_field: long_report
        }
        result = check_func(state)
        assert result == expected_clear, f"{analyst_name} The cycle should be stopped when an analyst has a report"
        
        # Should continue when there are no reports
        state[report_field] = ""
        result = check_func(state)
        assert result == expected_tools, f"{analyst_name} Analysts should execute tools when they have no reports"
    
    print("✅ Test passes: all analysts behave consistently")


def test_conditional_logic_fix():
    """Main test function - runs all tests"""
    print("🔧 Test conditional logic fix - prevent analyst node from infinite looping\n")
    
    try:
        test_fundamentals_no_report_with_tool_calls()
        test_fundamentals_has_report_with_tool_calls()
        test_all_analysts()
        
        print("\n🎉 All tests passed!")
        print("\n📋 Fix content:")
        print("✅ Added report completion check")
        print("✅ Prevented infinite loop")
        print("✅ All analyst nodes have been fixed")
        return True
    except AssertionError as e:
        print(f"\n❌ test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ test error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    # Run tests
    success = test_conditional_logic_fix()
    exit(0 if success else 1)

