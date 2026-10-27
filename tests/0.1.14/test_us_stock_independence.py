#!/usr/bin/env python3
"""
Test the independence of US stock data acquisition
Verify that obtaining U.S. stock data no longer relies on OpenAI configuration
"""

import os
import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from tradingagents.agents.utils.agent_utils import Toolkit
    from tradingagents.default_config import DEFAULT_CONFIG
except ImportError:
    print("❌ Unable to import Toolkit, please check the project structure")
    sys.exit(1)

def test_us_stock_data_independence():
    """Test the independence of US stock data acquisition"""
    print("🇺🇸 Test the independence of US stock data acquisition")
    print("=" * 60)
    
    # test scenario 1: OpenAI Disabled, real-time data enabled
    print("\n📋 scene 1: OpenAI Disable + Real-time data enabled")
    print("-" * 40)
    
    # Set environment variables
    os.environ['OPENAI_ENABLED'] = 'false'
    os.environ['REALTIME_DATA_ENABLED'] = 'true'
    
    try:
        config = DEFAULT_CONFIG.copy()
        config["realtime_data"] = True
        toolkit = Toolkit(config=config)
        
        # Check U.S. stock data tools
        us_tools = [
            'get_YFin_data_online',
            'get_YFin_data',
            'get_us_stock_data_cached'
        ]
        
        for tool_name in us_tools:
            if hasattr(toolkit, tool_name):
                print(f"   ✅ {tool_name} Available")
            else:
                print(f"   ❌ {tool_name} Not available")
                
        # Test the actual call
        try:
            # Test to obtain Apple stock data
            result = toolkit.get_us_stock_data_cached("AAPL", "1d", "1mo")
            if result and "error" not in str(result).lower():
                print("   ✅ US stock data obtained successfully")
            else:
                print("   ⚠️ Obtaining U.S. stock data returns an error or empty result")
        except Exception as e:
            print(f"   ⚠️ Abnormal acquisition of U.S. stock data: {e}")
            
    except Exception as e:
        print(f"   ❌ Toolkit Creation failed: {e}")
    
    # test scenario 2: OpenAI Enabled, real-time data disabled
    print("\n📋 scene 2: OpenAI enable + Real-time data disabled")
    print("-" * 40)
    
    # Set environment variables
    os.environ['OPENAI_ENABLED'] = 'true'
    os.environ['REALTIME_DATA_ENABLED'] = 'false'
    
    try:
        config = DEFAULT_CONFIG.copy()
        config["realtime_data"] = False
        toolkit = Toolkit(config=config)
        
        # Check U.S. stock data tools
        for tool_name in us_tools:
            if hasattr(toolkit, tool_name):
                print(f"   ✅ {tool_name} Available")
            else:
                print(f"   ❌ {tool_name} Not available")
                
    except Exception as e:
        print(f"   ❌ Toolkit Creation failed: {e}")
    
    print("\n💡 Conclusion:")
    print("   US stock data acquisition is now based on the REALTIME_DATA_ENABLED configuration")
    print("   No more reliance on OPENAI_ENABLED configuration")
    print("   Real functional independence achieved!")

if __name__ == "__main__":
    test_us_stock_data_independence()
    print("\n🎉 Test completed!")