#!/usr/bin/env python3
"""
Test configuration loading problem
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

def test_pricing_config_loading():
    """Test pricing configuration loading"""
    print("🔧 Test pricing configuration loading")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        # Create configuration manager
        config_manager = ConfigManager()
        
        print(f"📁 Configuration directory: {config_manager.config_dir}")
        print(f"📄 pricing document: {config_manager.pricing_file}")
        print(f"📄 Pricing file exists: {config_manager.pricing_file.exists()}")
        
        # Read file content directly
        if config_manager.pricing_file.exists():
            with open(config_manager.pricing_file, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"📄 File content length: {len(content)}")
            
            import json
            data = json.loads(content)
            print(f"📊 JSON The number of configurations in: {len(data)}")
            
            for i, config in enumerate(data, 1):
                print(f"   {i}. {config['provider']}/{config['model_name']}")
        
        # Load using ConfigManager
        print(f"\n📊 Load using ConfigManager:")
        pricing_configs = config_manager.load_pricing()
        print(f"📊 Number of configurations loaded: {len(pricing_configs)}")
        
        for i, config in enumerate(pricing_configs, 1):
            print(f"   {i}. {config.provider}/{config.model_name}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"\n📊 DeepSeek Configuration quantity: {len(deepseek_configs)}")
        
        # Find Bailian configuration
        dashscope_configs = [p for p in pricing_configs if p.provider == "dashscope"]
        print(f"📊 Bailian configuration quantity: {len(dashscope_configs)}")
        for config in dashscope_configs:
            print(f"   - {config.model_name}")
        
        return True
        
    except Exception as e:
        print(f"❌ Configuration load test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_cost_calculation():
    """Test cost calculation"""
    print("\n💰 Test cost calculation")
    print("=" * 50)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        config_manager = ConfigManager()
        
        # Testing DeepSeek Cost Calculation
        print("🤖 Testing DeepSeek Cost Calculation:")
        deepseek_cost = config_manager.calculate_cost(
            provider="deepseek",
            model_name="deepseek-chat",
            input_tokens=1000,
            output_tokens=500
        )
        print(f"   DeepSeek cost: ¥{deepseek_cost:.6f}")
        
        # Test Hundred Refining Cost Calculation
        print("🌟 Test Hundred Refining Cost Calculation:")
        dashscope_cost1 = config_manager.calculate_cost(
            provider="dashscope",
            model_name="qwen-plus",
            input_tokens=1000,
            output_tokens=500
        )
        print(f"   qwen-plus cost: ¥{dashscope_cost1:.6f}")
        
        dashscope_cost2 = config_manager.calculate_cost(
            provider="dashscope",
            model_name="qwen-plus-latest",
            input_tokens=1000,
            output_tokens=500
        )
        print(f"   qwen-plus-latest cost: ¥{dashscope_cost2:.6f}")
        
        return True
        
    except Exception as e:
        print(f"❌ Costing test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Debugging configuration loading issues")
    print("=" * 80)
    
    # Test configuration loading
    loading_success = test_pricing_config_loading()
    
    # Test cost calculation
    calc_success = test_cost_calculation()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    print(f"Configuration loading: {'✅ normal' if loading_success else '❌ There is a problem'}")
    print(f"cost calculation: {'✅ normal' if calc_success else '❌ There is a problem'}")
    
    overall_success = loading_success and calc_success
    
    if overall_success:
        print("\n🎉 The configuration system works fine!")
        print("   If you still have problems in actual use, it may be:")
        print("   1. Different configuration directories are used")
        print("   2. Configuration is cached")
        print("   3. The model name was modified somewhere")
    else:
        print("\n❌ There is a problem with the configuration system and needs to be repaired")
    
    print("\n🎯 Test completed!")
    return overall_success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
