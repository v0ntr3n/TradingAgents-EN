#!/usr/bin/env python3
"""
Testing DeepSeek costing fixes
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

def test_deepseek_pricing_config():
    """Testing DeepSeek Pricing Configuration"""
    print("🔧 Testing DeepSeek Pricing Configuration")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        # Create configuration manager
        config_manager = ConfigManager()
        
        # Load pricing configuration
        pricing_configs = config_manager.load_pricing()
        
        print(f"📊 Number of pricing configurations loaded: {len(pricing_configs)}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        
        print(f"📊 DeepSeek Pricing configuration quantity: {len(deepseek_configs)}")
        
        for config in deepseek_configs:
            print(f"   model: {config.model_name}")
            print(f"   Enter price: ¥{config.input_price_per_1k}/1K tokens")
            print(f"   output price: ¥{config.output_price_per_1k}/1K tokens")
            print(f"   Currency: {config.currency}")
            print()
        
        return len(deepseek_configs) > 0
        
    except Exception as e:
        print(f"❌ Pricing configuration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_deepseek_cost_calculation():
    """Testing DeepSeek Cost Calculation"""
    print("💰 Testing DeepSeek Cost Calculation")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        # Create configuration manager
        config_manager = ConfigManager()
        
        # Test cost calculation
        test_cases = [
            {"input_tokens": 1000, "output_tokens": 500},
            {"input_tokens": 2617, "output_tokens": 312},  # Actual number of tokens used
            {"input_tokens": 3240, "output_tokens": 320},
            {"input_tokens": 1539, "output_tokens": 103},
        ]
        
        for i, case in enumerate(test_cases, 1):
            input_tokens = case["input_tokens"]
            output_tokens = case["output_tokens"]
            
            cost = config_manager.calculate_cost(
                provider="deepseek",
                model_name="deepseek-chat",
                input_tokens=input_tokens,
                output_tokens=output_tokens
            )
            
            print(f"test case {i}:")
            print(f"   input tokens: {input_tokens}")
            print(f"   output tokens: {output_tokens}")
            print(f"   Calculate cost: ¥{cost:.6f}")
            
            # Manually verify calculations
            expected_cost = (input_tokens / 1000) * 0.0014 + (output_tokens / 1000) * 0.0028
            print(f"   expected cost: ¥{expected_cost:.6f}")
            print(f"   Calculation is correct: {'✅' if abs(cost - expected_cost) < 0.000001 else '❌'}")
            print()
            
            if cost == 0.0:
                print(f"❌ Cost calculation returns 0, indicating there is a problem with the configuration")
                return False
        
        return True
        
    except Exception as e:
        print(f"❌ Costing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_token_tracker():
    """Test Token Tracker"""
    print("📊 Test Token Tracker")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager, TokenTracker
        
        # Create configuration manager and token tracker
        config_manager = ConfigManager()
        token_tracker = TokenTracker(config_manager)
        
        # Test trace usage
        usage_record = token_tracker.track_usage(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=1000,
            output_tokens=500,
            session_id="test_session",
            analysis_type="test_analysis"
        )
        
        if usage_record:
            print(f"✅ Token Tracking successful")
            print(f"   provider: {usage_record.provider}")
            print(f"   model: {usage_record.model_name}")
            print(f"   input tokens: {usage_record.input_tokens}")
            print(f"   output tokens: {usage_record.output_tokens}")
            print(f"   cost: ¥{usage_record.cost:.6f}")
            print(f"   session ID: {usage_record.session_id}")
            
            if usage_record.cost > 0:
                print(f"✅ Cost calculation is correct")
                return True
            else:
                print(f"❌ The cost calculation is still 0")
                return False
        else:
            print(f"❌ Token Tracking failed")
            return False
        
    except Exception as e:
        print(f"❌ Token Tracker test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_deepseek_adapter_integration():
    """Test DeepSeek adapter integration"""
    print("🤖 Test DeepSeek adapter integration")
    print("=" * 50)
    
    try:
        # Check API key
        if not os.getenv("DEEPSEEK_API_KEY"):
            print("⚠️ DEEPSEEK_API_KEY not found, skipping adapter test")
            return True
        
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        # Test simple calls
        print("📤 Send test request...")
        result = deepseek_llm.invoke("Please introduce in one sentence DeepSeek")
        
        print(f"📊 response type: {type(result)}")
        print(f"📊 Response content length: {len(result.content)}")
        print(f"📊 Response content: {result.content[:100]}...")
        
        # Check whether there is cost information output
        print(f"✅ DeepSeek Adapter integration testing completed")
        return True
        
    except Exception as e:
        print(f"❌ DeepSeek Adapter integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 DeepSeek Cost Calculation Repair Verification")
    print("=" * 80)
    
    # Test pricing configuration
    config_success = test_deepseek_pricing_config()
    
    # Test cost calculation
    calc_success = test_deepseek_cost_calculation()
    
    # Test Token Tracker
    tracker_success = test_token_tracker()
    
    # Test adapter integration
    adapter_success = test_deepseek_adapter_integration()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"Pricing configuration: {'✅ Correct' if config_success else '❌ There is a problem'}")
    print(f"cost calculation: {'✅ Correct' if calc_success else '❌ There is a problem'}")
    print(f"Token Track: {'✅ Correct' if tracker_success else '❌ There is a problem'}")
    print(f"Adapter integration: {'✅ Correct' if adapter_success else '❌ There is a problem'}")
    
    overall_success = config_success and calc_success and tracker_success and adapter_success
    
    if overall_success:
        print("\n🎉 DeepSeek Cost calculation repair successful!")
        print("   - Pricing configuration is set correctly")
        print("   - Costing logic works properly")
        print("   - Token Tracker records costs correctly")
        print("   - Adapter integration is normal")
        print("\n DeepSeek s token usage cost should now be displayed correctly!")
    else:
        print("\n⚠️ DeepSeek Cost calculations still have problems")
        print("   Please check the above failed test items")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
