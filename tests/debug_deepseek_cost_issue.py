#!/usr/bin/env python3
"""
Debugging DeepSeek costing issues
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

def debug_config_manager():
    """Debug Configuration Manager"""
    print("🔧 Debug Configuration Manager")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        # Create configuration manager
        config_manager = ConfigManager()
        
        print(f"📁 Configuration directory: {config_manager.config_dir}")
        print(f"📄 pricing document: {config_manager.pricing_file}")
        print(f"📄 Pricing file exists: {config_manager.pricing_file.exists()}")
        
        # Load pricing configuration
        pricing_configs = config_manager.load_pricing()
        print(f"📊 Number of pricing configurations loaded: {len(pricing_configs)}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"📊 DeepSeek Pricing configuration quantity: {len(deepseek_configs)}")
        
        for config in deepseek_configs:
            print(f"   - provider: {config.provider}")
            print(f"   - model: {config.model_name}")
            print(f"   - Enter price: {config.input_price_per_1k}")
            print(f"   - output price: {config.output_price_per_1k}")
            print(f"   - Currency: {config.currency}")
        
        # Test cost calculation
        print(f"\n💰 Test cost calculation:")
        cost = config_manager.calculate_cost(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=2272,
            output_tokens=1215
        )
        print(f"   Calculation result: ¥{cost:.6f}")
        
        if cost == 0.0:
            print(f"❌ Cost calculation returns 0, check matching logic...")
            
            # Check the matching logic in detail
            for pricing in pricing_configs:
                print(f"   Check configuration: provider='{pricing.provider}', model='{pricing.model_name}'")
                if pricing.provider == "deepseek" and pricing.model_name == "deepseek-chat":
                    print(f"   ✅ Matching configuration found!")
                    input_cost = (2272 / 1000) * pricing.input_price_per_1k
                    output_cost = (1215 / 1000) * pricing.output_price_per_1k
                    total_cost = input_cost + output_cost
                    print(f"   Enter cost: {input_cost:.6f}")
                    print(f"   Output cost: {output_cost:.6f}")
                    print(f"   total cost: {total_cost:.6f}")
                    break
            else:
                print(f"   ❌ No matching configuration found")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration manager debugging failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def debug_token_tracker():
    """Debugging the Token Tracker"""
    print("\n📊 Debugging the Token Tracker")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager, TokenTracker
        
        # Create configuration manager and token tracker
        config_manager = ConfigManager()
        token_tracker = TokenTracker(config_manager)
        
        print(f"🔧 Token Tracker created successfully")
        
        # Check settings
        settings = config_manager.load_settings()
        cost_tracking_enabled = settings.get("enable_cost_tracking", True)
        print(f"📊 Cost tracking enabled: {cost_tracking_enabled}")
        
        # Test trace usage
        print(f"💰 Test Token Tracking...")
        usage_record = token_tracker.track_usage(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=2272,
            output_tokens=1215,
            session_id="debug_session",
            analysis_type="debug_analysis"
        )
        
        if usage_record:
            print(f"✅ Token Tracking successful")
            print(f"   provider: {usage_record.provider}")
            print(f"   model: {usage_record.model_name}")
            print(f"   input tokens: {usage_record.input_tokens}")
            print(f"   output tokens: {usage_record.output_tokens}")
            print(f"   cost: ¥{usage_record.cost:.6f}")
            
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
        print(f"❌ Token Tracker debugging failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def debug_deepseek_adapter():
    """Debugging the DeepSeek adapter"""
    print("\n🤖 Debugging the DeepSeek adapter")
    print("=" * 50)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("⚠️ DEEPSEEK_API_KEY not found, skipping adapter debugging")
        return True
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        print(f"🔧 Create DeepSeek adapter...")
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        print(f"📊 Model name: {deepseek_llm.model_name}")
        
        # Check TOKEN_TRACKING_ENABLED
        from tradingagents.llm_adapters.deepseek_adapter import TOKEN_TRACKING_ENABLED
        print(f"📊 Token Tracking enabled: {TOKEN_TRACKING_ENABLED}")
        
        # test call
        print(f"📤 Send test request...")
        result = deepseek_llm.invoke("test")
        
        print(f"📊 Call completed")
        print(f"   response length: {len(result.content)}")
        
        return True
        
    except Exception as e:
        print(f"❌ DeepSeek Adapter debugging failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def debug_model_name_issue():
    """Debugging model name matching issues"""
    print("\n🔍 Debugging model name matching issues")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        # Create configuration manager
        config_manager = ConfigManager()
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(model="deepseek-chat")
        
        print(f"📊 model name in adapter: '{deepseek_llm.model_name}'")
        
        # Load pricing configuration
        pricing_configs = config_manager.load_pricing()
        
        print(f"📊 DeepSeek model in pricing configuration:")
        for config in pricing_configs:
            if config.provider == "deepseek":
                print(f"   - Model name: '{config.model_name}'")
                print(f"   - Match check: {config.model_name == deepseek_llm.model_name}")
        
        # Manually test matches
        print(f"\n💰 Manual test costing:")
        cost = config_manager.calculate_cost(
            provider="deepseek",
            model_name=deepseek_llm.model_name,
            input_tokens=100,
            output_tokens=50
        )
        print(f"   Using adapter model name: ¥{cost:.6f}")
        
        cost2 = config_manager.calculate_cost(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=100,
            output_tokens=50
        )
        print(f"   Use hardcoded model names: ¥{cost2:.6f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Model name debugging failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 DeepSeek In-depth debugging of cost calculation issues")
    print("=" * 80)
    
    # Debug Configuration Manager
    config_success = debug_config_manager()
    
    # Debugging the Token Tracker
    tracker_success = debug_token_tracker()
    
    # Debug model name matching
    model_success = debug_model_name_issue()
    
    # debug adapter
    adapter_success = debug_deepseek_adapter()
    
    # Summary
    print("\n📋 Debugging summary")
    print("=" * 60)
    
    print(f"configuration manager: {'✅ normal' if config_success else '❌ There is a problem'}")
    print(f"Token tracker: {'✅ normal' if tracker_success else '❌ There is a problem'}")
    print(f"Model name match: {'✅ normal' if model_success else '❌ There is a problem'}")
    print(f"Adapter debugging: {'✅ normal' if adapter_success else '❌ There is a problem'}")
    
    overall_success = config_success and tracker_success and model_success and adapter_success
    
    if overall_success:
        print("\n🤔 All components are fine, but in actual use the cost is 0...")
        print("   possible reasons:")
        print("   1. Different configuration directories are used in the actual analysis process")
        print("   2. Configuration is overridden somewhere")
        print("   3. Have caching issues")
        print("   4. The model name was modified somewhere")
    else:
        print("\n❌ Problem found, please check the failed component above")
    
    print("\n🎯 Debugging completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
