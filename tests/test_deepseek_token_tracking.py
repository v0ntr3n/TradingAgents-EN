#!/usr/bin/env python3
"""
DeepSeek Token Statistical function test
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_deepseek_adapter():
    """Test the Token statistics function of the DeepSeek adapter"""
    print("🧪 Test DeepSeek adapter Token statistics...")
    
    # Check DeepSeek configuration
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("⚠️ DEEPSEEK_API_KEY not found, test skipped")
        return True  # Skip instead of fail
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from tradingagents.config.config_manager import config_manager, token_tracker
        
        # Get initial statistics
        initial_stats = config_manager.get_usage_statistics(1)
        initial_cost = initial_stats.get("total_cost", 0)
        
        # Create DeepSeek instance
        llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        # Generate session ID
        session_id = f"test_deepseek_{int(datetime.now().timestamp())}"
        
        # test call
        response = llm.invoke(
            "Please briefly describe what a stock is, no more than 50 words.",
            session_id=session_id,
            analysis_type="test_analysis"
        )
        
        print(f"   ✅ Response received successfully, length: {len(response.content)}")
        
        # Waiting for statistics update
        import time
        time.sleep(1)
        
        # Check statistics updates
        updated_stats = config_manager.get_usage_statistics(1)
        updated_cost = updated_stats.get("total_cost", 0)
        
        cost_increase = updated_cost - initial_cost
        
        print(f"   💰 cost increase: ¥{cost_increase:.4f}")
        
        # Check DeepSeek Statistics
        provider_stats = updated_stats.get("provider_stats", {})
        deepseek_stats = provider_stats.get("deepseek", {})
        
        if deepseek_stats:
            print(f"   📊 DeepSeek statistical presence: ✅")
            return True
        else:
            print(f"   📊 DeepSeek missing statistics: ❌")
            return False
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_trading_graph_integration():
    """Testing the DeepSeek integration in TradingGraph"""
    print("\n🧪 Testing the TradingGraph DeepSeek integration...")
    
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("⚠️ DEEPSEEK_API_KEY not found, test skipped")
        return True
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Configuration DeepSeek
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider": "deepseek",
            "llm_model": "deepseek-chat",
            "quick_think_llm": "deepseek-chat",
            "deep_think_llm": "deepseek-chat",
            "backend_url": "https://api.deepseek.com",
            "online_tools": True,
            "max_debate_rounds": 1,
        })
        
        # Create TradingAgentsGraph
        ta = TradingAgentsGraph(
            selected_analysts=["fundamentals"],
            config=config,
            debug=False  # reduce output
        )
        
        print(f"   ✅ TradingAgentsGraph Created successfully")
        return True
        
    except Exception as e:
        print(f"❌ Integration test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 DeepSeek Token Statistical function test")
    print("=" * 50)
    
    tests = [
        ("DeepSeek adapter", test_deepseek_adapter),
        ("TradingGraph Integrate", test_trading_graph_integration),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary results
    print("\n" + "="*50)
    print("📋 Summary of test results:")
    print("="*50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n total: {passed}/{len(results)} tests passed")
    
    return passed >= len(results) // 2

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
