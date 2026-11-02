#!/usr/bin/env python3
"""
Debugging DeepSeek costing issues
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_pricing_config():
    """Test pricing configuration"""
    print("🔍 Test pricing configuration...")
    
    from tradingagents.config.config_manager import ConfigManager
    
    config_manager = ConfigManager()
    pricing_configs = config_manager.load_pricing()
    
    print(f"📊 loaded {len(pricing_configs)} pricing configuration:")
    for pricing in pricing_configs:
        if pricing.provider == "deepseek":
            print(f"   ✅ {pricing.provider}/{pricing.model_name}: input¥{pricing.input_price_per_1k}/1K, output¥{pricing.output_price_per_1k}/1K")

def test_cost_calculation():
    """Test cost calculation"""
    print("\n🧮 Test cost calculation...")
    
    from tradingagents.config.config_manager import ConfigManager
    
    config_manager = ConfigManager()
    
    # Testing DeepSeek Cost Calculation
    test_cases = [
        ("deepseek", "deepseek-chat", 2000, 1000),
        ("deepseek", "deepseek-coder", 1500, 800),
        ("dashscope", "qwen-turbo", 2000, 1000),  # comparison test
    ]
    
    for provider, model, input_tokens, output_tokens in test_cases:
        cost = config_manager.calculate_cost(provider, model, input_tokens, output_tokens)
        print(f"   {provider}/{model}: {input_tokens}+{output_tokens} tokens = ¥{cost:.6f}")

def test_token_tracking():
    """Test Token Tracking"""
    print("\n📝 Test Token Tracking...")
    
    from tradingagents.config.config_manager import token_tracker
    
    # Test DeepSeek usage records
    record = token_tracker.track_usage(
        provider="deepseek",
        model_name="deepseek-chat",
        input_tokens=2000,
        output_tokens=1000,
        session_id="debug_test_001",
        analysis_type="debug_test"
    )
    
    if record:
        print(f"   ✅ Record created successfully:")
        print(f"      Provider: {record.provider}")
        print(f"      Model: {record.model_name}")
        print(f"      Tokens: {record.input_tokens}+{record.output_tokens}")
        print(f"      Cost: ¥{record.cost:.6f}")
    else:
        print(f"   ❌ Record creation failed")

def test_deepseek_adapter():
    """Test the DeepSeek adapter"""
    print("\n🤖 Test the DeepSeek adapter...")
    
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    if not deepseek_key:
        print("   ⚠️ DEEPSEEK_API_KEY not found, skipping adapter test")
        return
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        
        # Create DeepSeek instance
        llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=100
        )
        
        print(f"   ✅ DeepSeek Adapter created successfully")
        print(f"      Model: {llm.model_name}")
        print(f"      Base URL: {llm.openai_api_base}")
        
        # Test simple calls
        response = llm.invoke(
            "Please briefly describe what a stock is, no more than 30 words.",
            session_id="debug_adapter_test",
            analysis_type="debug_test"
        )
        
        print(f"   ✅ API Call successful, response length: {len(response.content)}")
        
    except Exception as e:
        print(f"   ❌ DeepSeek Adapter test failed: {e}")

def check_usage_statistics():
    """Check usage statistics"""
    print("\n📊 Check usage statistics...")
    
    from tradingagents.config.config_manager import config_manager
    
    stats = config_manager.get_usage_statistics(1)
    
    print(f"   total cost: ¥{stats.get('total_cost', 0):.6f}")
    print(f"   total requests: {stats.get('total_requests', 0)}")
    print(f"   total Token: {stats.get('total_tokens', 0)}")
    
    provider_stats = stats.get('provider_stats', {})
    deepseek_stats = provider_stats.get('deepseek', {})
    
    if deepseek_stats:
        print(f"   DeepSeek statistics:")
        print(f"      cost: ¥{deepseek_stats.get('cost', 0):.6f}")
        print(f"      Request: {deepseek_stats.get('requests', 0)}")
        print(f"      Token: {deepseek_stats.get('tokens', 0)}")
    else:
        print(f"   ❌ DeepSeek statistics not found")

def main():
    """main function"""
    print("🔧 DeepSeek Cost calculation debugging")
    print("=" * 50)
    
    try:
        test_pricing_config()
        test_cost_calculation()
        test_token_tracking()
        test_deepseek_adapter()
        check_usage_statistics()
        
        print("\n" + "=" * 50)
        print("✅ Debugging completed")
        
    except Exception as e:
        print(f"\n❌ An error occurred during debugging: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
