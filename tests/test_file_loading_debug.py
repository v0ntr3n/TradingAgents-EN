#!/usr/bin/env python3
"""
Debug file loading issues
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

def test_file_loading():
    """Test file loading"""
    print("🔬 File loading debugging")
    print("=" * 80)
    
    try:
        from tradingagents.config.config_manager import ConfigManager
        
        print("🔧 Create ConfigManager...")
        config_manager = ConfigManager()
        
        print("\n📊 Load pricing configuration...")
        print("=" * 60)
        
        # This triggers detailed file load logs
        pricing_configs = config_manager.load_pricing()
        
        print("=" * 60)
        print(f"📊 The final number of configurations loaded: {len(pricing_configs)}")
        
        # Find DeepSeek configuration
        deepseek_configs = [p for p in pricing_configs if p.provider == "deepseek"]
        print(f"📊 DeepSeek Configuration quantity: {len(deepseek_configs)}")
        
        if deepseek_configs:
            print("✅ Find DeepSeek configuration:")
            for config in deepseek_configs:
                print(f"   - {config.model_name}: input¥{config.input_price_per_1k}/1K, output¥{config.output_price_per_1k}/1K")
        else:
            print("❌ DeepSeek configuration not found")
        
        return True
        
    except Exception as e:
        print(f"❌ File loading test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 File loading debugging test")
    print("=" * 80)
    print("📝 This test will show the actual loaded configuration file contents")
    print("=" * 80)
    
    success = test_file_loading()
    
    if success:
        print("\n🎉 File loading test completed!")
        print("Please review the detailed log above to confirm the loaded file contents.")
    else:
        print("\n❌ File loading test failed")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
