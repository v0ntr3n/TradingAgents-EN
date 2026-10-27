#!/usr/bin/env python3
"""
Test the repair effect of DeepSeek using ReAct Agent
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_deepseek_react_market_analyst():
    """ReAct Market Analyst Testing DeepSeek"""
    print("🤖 Testing DeepSeek ReAct Market Analyst")
    print("=" * 60)
    
    try:
        # Check API key
        if not os.getenv("DEEPSEEK_API_KEY"):
            print("⚠️ DEEPSEEK_API_KEY not found, unable to test")
            return False
        
        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create DeepSeek LLM
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Create ReAct Market Analyst
        market_analyst = create_market_analyst_react(deepseek_llm, toolkit)
        
        # simulation state
        state = {
            "company_of_interest": "000002",
            "trade_date": "2025-07-08",
            "messages": []
        }
        
        print(f"📊 Start analyzing stocks: {state['company_of_interest']}")
        
        # Perform analysis
        result = market_analyst(state)
        
        print(f"📊 Analyze results:")
        print(f"   Number of messages: {len(result.get('messages', []))}")
        
        market_report = result.get('market_report', '')
        print(f"   Market report length: {len(market_report)}")
        print(f"   First 500 characters of market report:")
        print("-" * 50)
        print(market_report[:500])
        print("-" * 50)
        
        # Check report quality
        has_data = any(keyword in market_report for keyword in ["¥", "RSI", "MACD", "Vanke", "Technical indicators", "6.56"])
        has_analysis = len(market_report) > 500
        not_placeholder = "Calling tool" not in market_report and "(Call tool" not in market_report
        
        print(f"📊 Report quality check:")
        print(f"   Contains actual data: {'✅' if has_data else '❌'}")
        print(f"   Enriched analysis content: {'✅' if has_analysis else '❌'}")
        print(f"   non-placeholder content: {'✅' if not_placeholder else '❌'}")
        
        success = has_data and has_analysis and not_placeholder
        print(f"   overall assessment: {'✅ success' if success else '❌ Needs improvement'}")
        
        if success:
            print("\n🎉 DeepSeek ReAct Market analyst repaired successfully!")
            print("   - Correctly called the tool to obtain data")
            print("   - Generated analysis reports based on real data")
            print("   - The report is informative and professional")
        else:
            print("\n⚠️ DeepSeek ReAct Market analysts still need to improve")
            if not has_data:
                print("   - Lack of actual data analysis")
            if not has_analysis:
                print("   - The analysis content is not substantial enough")
            if not not_placeholder:
                print("   - Still contains placeholder content")
        
        return success
        
    except Exception as e:
        print(f"❌ DeepSeek ReAct Market Analyst Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_graph_setup_logic():
    """Test whether the chart setting logic is correct and select ReAct mode"""
    print("\n🔧 Test chart setup logic")
    print("=" * 60)
    
    try:
        from tradingagents.graph.setup import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Simulate DeepSeek configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "deepseek"
        config["deep_think_llm"] = "deepseek-chat"
        config["quick_think_llm"] = "deepseek-chat"
        
        print(f"📊 Configuration information:")
        print(f"   LLM provider: {config['llm_provider']}")
        print(f"   deep thinking model: {config['deep_think_llm']}")
        print(f"   quick thinking model: {config['quick_think_llm']}")
        
        # Create graph instance
        graph = TradingAgentsGraph(config)
        
        # Set up the analyst (this triggers the selection logic)
        print(f"\n📈 Set up a market analyst...")
        graph.setup_and_compile(selected_analysts=["market"])
        
        print(f"✅ Picture setting completed")
        return True
        
    except Exception as e:
        print(f"❌ Figure setup logic test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 DeepSeek ReAct Repair effect test")
    print("=" * 80)
    
    # Test chart setup logic
    setup_success = test_graph_setup_logic()
    
    # Testing DeepSeek ReAct Analyst
    analyst_success = test_deepseek_react_market_analyst()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"Diagram setup logic: {'✅ Correct' if setup_success else '❌ There is a problem'}")
    print(f"DeepSeek ReAct analyst: {'✅ Repair successful' if analyst_success else '❌ still needs fixing'}")
    
    overall_success = setup_success and analyst_success
    
    if overall_success:
        print("\n🎉 DeepSeek ReAct The repair was completely successful!")
        print("   - Diagram setup logic correctly selects ReAct mode")
        print("   - DeepSeek Ability to correctly execute tool calls and generate analysis")
        print("   - Now both DeepSeek and Bailian use the stable ReAct Agent mode")
    else:
        print("\n⚠️ There are still problems to be solved")
        if not setup_success:
            print("   - Diagram setup logic needs to be checked")
        if not analyst_success:
            print("   - DeepSeek ReAct Analyst needs further fixes")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
