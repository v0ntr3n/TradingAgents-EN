#!/usr/bin/env python3
"""
Actual test of DeepSeek cost calculation repair effect
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

def test_real_deepseek_analysis():
    """Test real-life DeepSeek stock analysis and watch cost calculations"""
    print("🧪 Practical test of DeepSeek cost calculation")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.agents.analysts.market_analyst import create_market_analyst_react
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        print("🔧 Initialize DeepSeek Analyst...")
        
        # Create DeepSeek LLM
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=1000
        )
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Create ReAct Market Analyst
        market_analyst = create_market_analyst_react(deepseek_llm, toolkit)
        
        print("📊 Start analyzing stocks 000002...")
        print("⏱️ Please observe the costing output...")
        print("-" * 50)
        
        # simulation state
        state = {
            "company_of_interest": "000002",
            "trade_date": "2025-07-08",
            "messages": []
        }
        
        # Perform analysis
        result = market_analyst(state)
        
        print("-" * 50)
        print("📋 Analysis completed!")
        
        market_report = result.get('market_report', '')
        print(f"📊 Market report length: {len(market_report)}")
        
        if len(market_report) > 500:
            print("✅ Analysis successfully generates detailed report")
            print(f"📄 Report first 200 characters: {market_report[:200]}...")
            return True
        else:
            print("❌ The analysis report is too short and there may be a problem")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_simple_deepseek_call():
    """Test a simple DeepSeek call and observe the cost"""
    print("\n🤖 Testing a simple DeepSeek call")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        print("🔧 Create DeepSeek instance...")
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=200
        )
        
        print("📤 Send test request...")
        print("⏱️ Please observe the costing output...")
        print("-" * 30)
        
        # test call
        result = deepseek_llm.invoke("Please briefly analyze the overall trend of the current A-share market in no more than 100 words.")
        
        print("-" * 30)
        print("📋 Call completed!")
        print(f"📊 response length: {len(result.content)}")
        print(f"📄 Response content: {result.content}")
        
        return True
        
    except Exception as e:
        print(f"❌ Simple call test fails: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_calls():
    """Test multiple calls and observe the cumulative cost"""
    print("\n🔄 Test multiple DeepSeek calls")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        print("🔧 Create DeepSeek instance...")
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        questions = [
            "What are stocks?",
            "What is technical analysis?",
            "What is fundamental analysis?"
        ]
        
        print(f"📤 send{len(questions)}test requests...")
        print("⏱️ Please observe the cost calculation for each call...")
        print("-" * 40)
        
        for i, question in enumerate(questions, 1):
            print(f"\n🔸 No.{i}calls: {question}")
            result = deepseek_llm.invoke(question)
            print(f"   response: {result.content[:50]}...")
        
        print("-" * 40)
        print("📋 Multiple calls completed!")
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed when called multiple times: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 DeepSeek Cost calculation practical test")
    print("=" * 80)
    print("📝 Pay attention to the cost information in the output:")
    print("   - Specific cost amounts should be shown (e.g.¥0.004537) ")
    print("   - should not be displayed¥0.000000")
    print("=" * 80)
    
    # Test simple calls
    simple_success = test_simple_deepseek_call()
    
    # Test multiple calls
    multiple_success = test_multiple_calls()
    
    # Test actual analysis (optional, more time-consuming)
    print(f"\n❓ Want to test out a complete stock analysis? (It takes more time, about 1-2 minutes)")
    print(f"   If you just want to verify the cost calculation, the previous test is enough.")
    
    # We skip the complete analysis here because it is more time consuming.
    analysis_success = True  # test_real_deepseek_analysis()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"simple call: {'✅ success' if simple_success else '❌ failed'}")
    print(f"Called multiple times: {'✅ success' if multiple_success else '❌ failed'}")
    print(f"full analysis: {'⏭️ skip' if analysis_success else '❌ failed'}")
    
    overall_success = simple_success and multiple_success
    
    if overall_success:
        print("\n🎉 DeepSeek Cost calculation test successful!")
        print("   If you see specific cost amounts in the output above")
        print("    (Such as¥0.004537 instead of¥0.000000) , ")
        print("   Then the costing repair is a success!")
    else:
        print("\n❌ DeepSeek Costing test failed")
        print("   Please check API key configuration and network connection")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
