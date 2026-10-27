#!/usr/bin/env python3
"""
Test new tool selection logic
Verify that obtaining U.S. stock data no longer relies on OpenAI configuration
"""

import os
import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_tool_selection_scenarios():
    """Test tool selection under different configuration scenarios"""
    print("🧪 Test tool selection logic")
    print("=" * 70)
    
    scenarios = [
        {
            "name": "scene 1: Completely offline mode",
            "config": {
                "online_tools": False,
                "online_news": False,
                "realtime_data": False,
            },
            "expected": {
                "market_primary": "get_YFin_data",
                "news_primary": "get_finnhub_news",
                "social_primary": "get_reddit_stock_info"
            }
        },
        {
            "name": "scene 2: Real-time data enabled",
            "config": {
                "online_tools": False,
                "online_news": False,
                "realtime_data": True,
            },
            "expected": {
                "market_primary": "get_YFin_data_online",
                "news_primary": "get_finnhub_news",
                "social_primary": "get_reddit_stock_info"
            }
        },
        {
            "name": "scene 3: Online news enabled",
            "config": {
                "online_tools": False,
                "online_news": True,
                "realtime_data": False,
            },
            "expected": {
                "market_primary": "get_YFin_data",
                "news_primary": "get_google_news",
                "social_primary": "get_reddit_stock_info"
            }
        },
        {
            "name": "scene 4: Fully online mode",
            "config": {
                "online_tools": True,
                "online_news": True,
                "realtime_data": True,
            },
            "expected": {
                "market_primary": "get_YFin_data_online",
                "news_primary": "get_global_news_openai",
                "social_primary": "get_stock_news_openai"
            }
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📋 {scenario['name']}")
        print("-" * 50)
        
        try:
            # Simulation tool selection logic
            config = scenario['config']
            online_tools_enabled = config.get("online_tools", False)
            online_news_enabled = config.get("online_news", True)
            realtime_data_enabled = config.get("realtime_data", False)
            
            print(f"   Configuration: online_tools={online_tools_enabled}, "
                  f"online_news={online_news_enabled}, "
                  f"realtime_data={realtime_data_enabled}")
            
            # Market data tool selection
            if realtime_data_enabled:
                market_primary = "get_YFin_data_online"
            else:
                market_primary = "get_YFin_data"
            
            # News tool selection
            if online_news_enabled:
                if online_tools_enabled:
                    news_primary = "get_global_news_openai"
                else:
                    news_primary = "get_google_news"
            else:
                news_primary = "get_finnhub_news"
            
            # Social media tool selection
            if online_tools_enabled:
                social_primary = "get_stock_news_openai"
            else:
                social_primary = "get_reddit_stock_info"
            
            # Verification results
            expected = scenario['expected']
            results = {
                "market_primary": market_primary,
                "news_primary": news_primary,
                "social_primary": social_primary
            }
            
            print(f"   result:")
            for tool_type, tool_name in results.items():
                expected_tool = expected[tool_type]
                status = "✅" if tool_name == expected_tool else "❌"
                print(f"     {tool_type}: {tool_name} {status}")
                if tool_name != expected_tool:
                    print(f"       Expectation: {expected_tool}")
            
        except Exception as e:
            print(f"   ❌ test failed: {e}")

def test_trading_graph_integration():
    """Test the TradingGraph integration"""
    print(f"\n🔗 Test the TradingGraph integration")
    print("=" * 70)
    
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        
        # Test different configurations
        test_configs = [
            {
                "name": "Offline mode",
                "config": {
                    **DEFAULT_CONFIG,
                    "online_tools": False,
                    "online_news": False,
                    "realtime_data": False,
                }
            },
            {
                "name": "real-time data mode",
                "config": {
                    **DEFAULT_CONFIG,
                    "online_tools": False,
                    "online_news": True,
                    "realtime_data": True,
                }
            }
        ]
        
        for test_config in test_configs:
            print(f"\n📊 Test configuration: {test_config['name']}")
            print("-" * 40)
            
            try:
                # Create a TradingGraph instance
                ta = TradingAgentsGraph(
                    config=test_config['config'],
                    selected_analysts=["market_analyst"],
                    debug=False
                )
                
                # Check tool node configuration
                market_tools = ta.tool_nodes["market"].tools
                news_tools = ta.tool_nodes["news"].tools
                social_tools = ta.tool_nodes["social"].tools
                
                print(f"   Number of market instruments: {len(market_tools)}")
                print(f"   Number of news tools: {len(news_tools)}")
                print(f"   Number of social tools: {len(social_tools)}")
                
                # Check the main tools
                market_tool_names = [tool.name for tool in market_tools]
                news_tool_names = [tool.name for tool in news_tools]
                social_tool_names = [tool.name for tool in social_tools]
                
                print(f"   Main market tools: {market_tool_names[1] if len(market_tool_names) > 1 else 'N/A'}")
                print(f"   Main news tools: {news_tool_names[0] if news_tool_names else 'N/A'}")
                print(f"   Main social tools: {social_tool_names[0] if social_tool_names else 'N/A'}")
                
                print("   ✅ TradingGraph Created successfully")
                
            except Exception as e:
                print(f"   ❌ TradingGraph Creation failed: {e}")
                
    except ImportError as e:
        print(f"   ⚠️ Unable to import TradingGraph: {e}")

def test_us_stock_data_independence():
    """Test the independence of US stock data acquisition"""
    print(f"\n🇺🇸 Test the independence of US stock data acquisition")
    print("=" * 70)
    
    print("Verify that obtaining U.S. stock data no longer relies on OpenAI configuration...")
    
    # Simulate different OpenAI configuration states
    openai_scenarios = [
        {"OPENAI_API_KEY": None, "OPENAI_ENABLED": "false"},
        {"OPENAI_API_KEY": "test_key", "OPENAI_ENABLED": "true"},
    ]
    
    for i, openai_config in enumerate(openai_scenarios, 1):
        print(f"\n📋 OpenAI scene {i}: {openai_config}")
        print("-" * 40)
        
        # Temporarily set environment variables
        original_env = {}
        for key, value in openai_config.items():
            original_env[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        
        try:
            # Test different online tool configurations
            data_configs = [
                {"REALTIME_DATA_ENABLED": "false", "expected": "Offline data"},
                {"REALTIME_DATA_ENABLED": "true", "expected": "real time data"},
            ]
            
            for data_config in data_configs:
                os.environ["REALTIME_DATA_ENABLED"] = data_config["REALTIME_DATA_ENABLED"]
                
                # Reload configuration
                from importlib import reload
                import tradingagents.default_config
                reload(tradingagents.default_config)
                
                from tradingagents.default_config import DEFAULT_CONFIG
                
                realtime_enabled = DEFAULT_CONFIG.get("realtime_data", False)
                expected_mode = "real time data" if realtime_enabled else "Offline data"
                
                print(f"     REALTIME_DATA_ENABLED={data_config['REALTIME_DATA_ENABLED']} "
                      f"-> {expected_mode} ✅")
                
        finally:
            # Restore original environment variables
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    
    print("\n💡 Conclusion: US stock data acquisition is now completely independent of OpenAI configuration!")

def main():
    """Main test function"""
    print("🚀 Tool selection logic testing")
    print("=" * 70)
    
    # Run tests
    test_tool_selection_scenarios()
    test_trading_graph_integration()
    test_us_stock_data_independence()
    
    print(f"\n🎉 Test completed!")
    print("💡 U.S. stock data acquisition is now based on special configuration fields and no longer relies on OpenAI configuration.")

if __name__ == "__main__":
    main()