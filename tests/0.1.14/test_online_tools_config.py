#!/usr/bin/env python3
"""
Test new online tool configuration system
Verify integration of environment variables and configuration files
"""

import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_online_tools_config():
    """Test online tool configuration"""
    print("🧪 Test online tool configuration system")
    print("=" * 60)
    
    # 1. Check environment variables
    print("\n📋 Environment variable check:")
    env_vars = {
        'ONLINE_TOOLS_ENABLED': os.getenv('ONLINE_TOOLS_ENABLED', 'not set'),
        'ONLINE_NEWS_ENABLED': os.getenv('ONLINE_NEWS_ENABLED', 'not set'),
        'REALTIME_DATA_ENABLED': os.getenv('REALTIME_DATA_ENABLED', 'not set'),
        'OPENAI_ENABLED': os.getenv('OPENAI_ENABLED', 'not set'),
    }
    
    for var, value in env_vars.items():
        status = "✅" if value != "not set" else "⚠️"
        print(f"   {status} {var}: {value}")
    
    # 2. Test configuration file reading
    print("\n🔧 Configuration file testing:")
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config_items = {
            'online_tools': DEFAULT_CONFIG.get('online_tools'),
            'online_news': DEFAULT_CONFIG.get('online_news'), 
            'realtime_data': DEFAULT_CONFIG.get('realtime_data'),
        }
        
        for key, value in config_items.items():
            print(f"   ✅ {key}: {value}")
            
    except Exception as e:
        print(f"   ❌ Failed to read configuration file: {e}")
        return False
    
    # 3. Test configuration logic
    print("\n🧠 Configure logical validation:")
    
    # Check the online tool master switch
    online_tools = DEFAULT_CONFIG.get('online_tools', False)
    online_news = DEFAULT_CONFIG.get('online_news', False)
    realtime_data = DEFAULT_CONFIG.get('realtime_data', False)
    
    print(f"   📊 Online tool master switch: {'🟢 enable' if online_tools else '🔴 Disable'}")
    print(f"   📰 Online news tools: {'🟢 enable' if online_news else '🔴 Disable'}")
    print(f"   📈 Real-time data acquisition: {'🟢 enable' if realtime_data else '🔴 Disable'}")
    
    # 4. Configuration recommendations
    print("\n💡 Configuration recommendations:")
    if not online_tools and not realtime_data:
        print("   ✅ Currently in offline mode, suitable for development and testing, saving API costs")
    elif online_tools and realtime_data:
        print("   ⚠️ It is currently in fully online mode, which will consume more API quotas.")
    else:
        print("   🔧 Currently in mixed mode, some functions are online and some are offline.")
    
    if online_news and not online_tools:
        print("   💡 Suggestion: The news tool is enabled but the main switch is turned off, which may cause functional conflicts")
    
    return True

def test_toolkit_integration():
    """Test toolkit integration"""
    print("\n🔗 Toolkit integration testing:")
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit instance
        toolkit = Toolkit(config=DEFAULT_CONFIG)
        print("   ✅ Toolkit Instance created successfully")
        
        # Check online tool availability
        online_tools = [
            'get_google_news',
            'get_reddit_news', 
            'get_reddit_stock_info',
            'get_chinese_social_sentiment'
        ]
        
        available_tools = []
        for tool_name in online_tools:
            if hasattr(toolkit, tool_name):
                available_tools.append(tool_name)
                print(f"   ✅ {tool_name} Available")
            else:
                print(f"   ❌ {tool_name} Not available")
        
        print(f"\n   📊 Available online tools: {len(available_tools)}/{len(online_tools)}")
        
        return len(available_tools) > 0
        
    except Exception as e:
        print(f"   ❌ Toolkit integration test failed: {e}")
        return False

def show_config_examples():
    """Show configuration example"""
    print("\n📝 Configuration example:")
    print("=" * 60)
    
    examples = {
        "development mode (Offline)": {
            "ONLINE_TOOLS_ENABLED": "false",
            "ONLINE_NEWS_ENABLED": "false", 
            "REALTIME_DATA_ENABLED": "false",
            "Description": "Completely offline, using cached data, saving costs"
        },
        "test mode (Partially online)": {
            "ONLINE_TOOLS_ENABLED": "false",
            "ONLINE_NEWS_ENABLED": "true",
            "REALTIME_DATA_ENABLED": "false", 
            "Description": "News online, data offline, balancing functionality and cost"
        },
        "production mode (completely online)": {
            "ONLINE_TOOLS_ENABLED": "true",
            "ONLINE_NEWS_ENABLED": "true",
            "REALTIME_DATA_ENABLED": "true",
            "Description": "Completely online, get the latest data, suitable for real trading"
        }
    }
    
    for mode, config in examples.items():
        print(f"\n🔧 {mode}:")
        for key, value in config.items():
            if key == "Description":
                print(f"   💡 {value}")
            else:
                print(f"   {key}={value}")

def main():
    """Main test function"""
    print("🚀 Online tool configuration system testing")
    print("=" * 70)
    
    # Run tests
    config_success = test_online_tools_config()
    toolkit_success = test_toolkit_integration()
    
    # Show configuration example
    show_config_examples()
    
    # Summary
    print("\n📊 Test summary:")
    print("=" * 60)
    print(f"   Configure the system: {'✅ normal' if config_success else '❌ Abnormal'}")
    print(f"   Toolkit integration: {'✅ normal' if toolkit_success else '❌ Abnormal'}")
    
    if config_success and toolkit_success:
        print("\n🎉 The online tool configuration system is running normally!")
        print("💡 You can now flexibly control online/offline mode via environment variables")
    else:
        print("\n⚠️ Found a problem, please check the configuration")
    
    return config_success and toolkit_success

if __name__ == "__main__":
    main()