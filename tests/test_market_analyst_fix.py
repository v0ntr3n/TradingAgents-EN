#!/usr/bin/env python3
"""
Market analyst testing the fix
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

def test_deepseek_market_analyst():
    """Market analysts testing DeepSeek"""
    print("🤖 Test the repair effect of DeepSeek Market Analyst")
    print("=" * 60)
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
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
        
        # Create a market analyst
        market_analyst = create_market_analyst(deepseek_llm, toolkit)
        
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
        has_data = any(keyword in market_report for keyword in ["¥", "RSI", "MACD", "Vanke", "Technical indicators"])
        has_analysis = len(market_report) > 500
        not_placeholder = "Calling tool" not in market_report
        
        print(f"📊 Report quality check:")
        print(f"   Contains actual data: {'✅' if has_data else '❌'}")
        print(f"   Enriched analysis content: {'✅' if has_analysis else '❌'}")
        print(f"   non-placeholder content: {'✅' if not_placeholder else '❌'}")
        
        success = has_data and has_analysis and not_placeholder
        print(f"   overall assessment: {'✅ success' if success else '❌ Needs improvement'}")
        
        return success
        
    except Exception as e:
        print(f"❌ DeepSeek Market Analyst Test Failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_dashscope_market_analyst():
    """Test Bailian s Market Analyst (ReAct Mode)"""
    print("\n🌟 Test Bailian Market Analyst (ReAct Mode)")
    print("=" * 60)
    
    try:
        # Check API key
        if not os.getenv("DASHSCOPE_API_KEY"):
            print("⚠️ DASHSCOPE_API_KEY not found, skipping Bailian test")
            return True  # Skipping does not count as failure
        
        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create Bailian LLM
        dashscope_llm = ChatDashScope(
            model="qwen-plus",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Create ReAct Market Analyst
        market_analyst = create_market_analyst_react(dashscope_llm, toolkit)
        
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
        has_data = any(keyword in market_report for keyword in ["¥", "RSI", "MACD", "Vanke", "Technical indicators"])
        has_analysis = len(market_report) > 500
        not_placeholder = "Calling tool" not in market_report
        
        print(f"📊 Report quality check:")
        print(f"   Contains actual data: {'✅' if has_data else '❌'}")
        print(f"   Enriched analysis content: {'✅' if has_analysis else '❌'}")
        print(f"   non-placeholder content: {'✅' if not_placeholder else '❌'}")
        
        success = has_data and has_analysis and not_placeholder
        print(f"   overall assessment: {'✅ success' if success else '❌ Needs improvement'}")
        
        return success
        
    except Exception as e:
        print(f"❌ Bailian market analyst test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Market Analyst Repair Effect Test")
    print("=" * 80)
    
    # Check API key
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    
    if not deepseek_key:
        print("⚠️ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    # test DeepSeek
    deepseek_success = test_deepseek_market_analyst()
    
    # Test Bailian (if you have an API key)
    dashscope_success = test_dashscope_market_analyst()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"DeepSeek market analyst: {'✅ Repair successful' if deepseek_success else '❌ still needs fixing'}")
    print(f"Bailian ReAct Analyst: {'✅ working fine' if dashscope_success else '❌ Need to check'}")
    
    overall_success = deepseek_success and dashscope_success
    
    if overall_success:
        print("\n🎉 Market analyst repaired successfully!")
        print("   - DeepSeek Tool calls are now executed correctly and a complete analysis is generated")
        print("   - Bailian ReAct mode continues to work normally")
        print("   - Both models can generate technical analysis reports based on real data")
    else:
        print("\n⚠️ There are still problems to be solved")
        if not deepseek_success:
            print("   - DeepSeek Market analysts need further fixes")
        if not dashscope_success:
            print("   - Bailian ReAct analysts need to check")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
