#!/usr/bin/env python3
"""
Debugging script for testing analysis level 3 infinite loop issues
"""

import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tradingagents.utils.logging_init import init_logging
init_logging()

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.graph.conditional_logic import ConditionalLogic
from tradingagents.agents.utils.agent_states import AgentState
from langchain_core.messages import AIMessage
from app.services.simple_analysis_service import create_analysis_config

def test_level3_deadlock():
    """Test analysis level 3 infinite loop problem"""
    
    print("=" * 80)
    print("🔍 Analysis level 3 infinite loop problem debugging")
    print("=" * 80)
    
    # 1. Compare different levels of configurations
    print("\n📊 1. Configuration comparison analysis")
    print("-" * 50)
    
    levels = [
        ("fast", 1, "1 level"),
        ("Basics", 2, "2 level"), 
        ("Standard", 3, "3 level")
    ]
    
    configs = {}
    for depth_name, level, desc in levels:
        config = create_analysis_config(
            research_depth=depth_name,
            selected_analysts=["market", "fundamentals"],
            quick_model="qwen-plus",
            deep_model="qwen-max",
            llm_provider="dashscope",
            market_type="A shares"
        )
        configs[level] = config
        
        print(f"\n{desc} ({depth_name}):")
        print(f"  - max_debate_rounds: {config['max_debate_rounds']}")
        print(f"  - max_risk_discuss_rounds: {config['max_risk_discuss_rounds']}")
        print(f"  - memory_enabled: {config['memory_enabled']}")
        print(f"  - online_tools: {config['online_tools']}")
    
    # 2. Analyze key differences
    print("\n🔍 2. Key difference analysis")
    print("-" * 50)
    
    # Special configuration for level 3
    level3_config = configs[3]
    level2_config = configs[2]
    level1_config = configs[1]
    
    print("The difference between level 3 and levels 1 and 2:")
    print(f"  - risk discussion round: level 1={level1_config['max_risk_discuss_rounds']}, level 2={level2_config['max_risk_discuss_rounds']}, level 3={level3_config['max_risk_discuss_rounds']}")
    print(f"  - memory function: level 1={level1_config['memory_enabled']}, level 2={level2_config['memory_enabled']}, level 3={level3_config['memory_enabled']}")
    print(f"  - Online tools: level 1={level1_config['online_tools']}, level 2={level2_config['online_tools']}, level 3={level3_config['online_tools']}")
    
    # 3. Simulate the conditional judgment of fundamental analysts
    print("\n🤖 3. Fundamental analyst conditional judgment simulation")
    print("-" * 50)
    
    # Create conditional logic instance
    conditional_logic = ConditionalLogic(
        max_debate_rounds=level3_config['max_debate_rounds'],
        max_risk_discuss_rounds=level3_config['max_risk_discuss_rounds']
    )
    
    # Simulate different status scenarios
    from langchain_core.messages.tool import ToolCall
    
    # Create correctly formatted tool_call
    tool_call = ToolCall(
        name="get_stock_fundamentals_unified",
        args={"ticker": "000001", "start_date": "2025-01-01", "end_date": "2025-01-15", "curr_date": "2025-01-15"},
        id="call_123"
    )
    
    scenarios = [
        {
            "name": "scene 1: Empty report + Yes tool_calls",
            "state": {
                "messages": [AIMessage(content="Analyzing...", tool_calls=[tool_call])],
                "fundamentals_report": ""
            }
        },
        {
            "name": "scene 2: Empty report + None tool_calls", 
            "state": {
                "messages": [AIMessage(content="Analysis completed")],
                "fundamentals_report": ""
            }
        },
        {
            "name": "scene 3: short report + Yes tool_calls",
            "state": {
                "messages": [AIMessage(content="Analyzing...", tool_calls=[tool_call])],
                "fundamentals_report": "short report"
            }
        },
        {
            "name": "scene 4: full report + Yes tool_calls",
            "state": {
                "messages": [AIMessage(content="Analysis completed", tool_calls=[tool_call])],
                "fundamentals_report": "This is a complete fundamental analysis report, including detailed financial data analysis, valuation model calculation, industry comparative analysis, etc. The total length exceeds 100 characters and should be considered a completed report."
            }
        },
        {
            "name": "scene 5: full report + None tool_calls",
            "state": {
                "messages": [AIMessage(content="Analysis completed")],
                "fundamentals_report": "This is a complete fundamental analysis report, including detailed financial data analysis, valuation model calculation, industry comparative analysis, etc. The total length exceeds 100 characters and should be considered a completed report."
            }
        }
    ]
    
    for scenario in scenarios:
        print(f"\n{scenario['name']}:")
        state = AgentState(scenario['state'])
        result = conditional_logic.should_continue_fundamentals(state)
        
        report_len = len(scenario['state']['fundamentals_report'])
        has_tool_calls = len(scenario['state']['messages']) > 0 and hasattr(scenario['state']['messages'][-1], 'tool_calls') and scenario['state']['messages'][-1].tool_calls
        
        print(f"  - Report length: {report_len}")
        print(f"  - Yes tool_calls: {has_tool_calls}")
        print(f"  - Conditional judgment result: {result}")
        
        # Analyze whether it may cause an infinite loop
        if result == "tools_fundamentals" and report_len == 0:
            print(f"  ⚠️  Possible risk of endless loop: Report is empty but continue to call the tool")
        elif result == "tools_fundamentals" and report_len > 100:
            print(f"  🚨 Potential endless loop: Report completed but tool still needs to be called!")
        else:
            print(f"  ✅ normal process")
    
    # 4. Check possible causes of infinite loops
    print("\n🔍 4. Analysis of causes of infinite loop")
    print("-" * 50)
    
    print("Possible causes of infinite loop:")
    print("1. Level 3 max_risk_discuss_rounds=2, Edge connections that may affect workflow diagrams")
    print("2. memory_enabled=True May cause state management issues")
    print("3. Fundamental analysts may use different tools to call strategies at level 3")
    print("4. Conditional judgment logic may have problems under certain configurations")
    
    # 5. Suggested fixes
    print("\n💡 5. Suggested fixes")
    print("-" * 50)
    
    print("Based on the analysis, it is recommended to check the following aspects:")
    print("1. Check if the fundamental analyst is set up correctly at level 3 fundamentals_report")
    print("2. Verify whether the conditional judgment logic correctly handles tool_calls and report status")
    print("3. Check the workflow diagram at max_risk_discuss_rounds=2 edge configuration")
    print("4. Verify Google tool call handler behavior at level 3")
    print("5. Add loop detection and timeout protection mechanism")
    
    print("\n" + "=" * 80)
    print("Debugging analysis completed")
    print("=" * 80)

if __name__ == "__main__":
    test_level3_deadlock()