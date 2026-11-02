#!/usr/bin/env python3
"""
Simplified analysis test script
Used to verify that TradingAgents core functionality is working properly
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_basic_imports():
    """Test basic import"""
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        print("✅ Basic import successful")
        return True
    except Exception as e:
        print(f"❌ Basic import failed: {e}")
        return False

def test_environment_variables():
    """Test environment variables"""
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    finnhub_key = os.getenv("FINNHUB_API_KEY")
    
    print(f"DASHSCOPE_API_KEY: {'Already set' if dashscope_key else 'not set'}")
    print(f"FINNHUB_API_KEY: {'Already set' if finnhub_key else 'not set'}")
    
    return bool(dashscope_key and finnhub_key)

def test_graph_initialization():
    """Test chart initialization"""
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "dashscope"
        config["deep_think_llm"] = "qwen-plus"
        config["quick_think_llm"] = "qwen-plus"
        config["memory_enabled"] = True
        config["online_tools"] = True
        
        # repair path
        config["data_dir"] = str(project_root / "data")
        config["results_dir"] = str(project_root / "results")
        config["data_cache_dir"] = str(project_root / "tradingagents" / "dataflows" / "data_cache")
        
        # Create directory
        os.makedirs(config["data_dir"], exist_ok=True)
        os.makedirs(config["results_dir"], exist_ok=True)
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        # Initialization diagram
        graph = TradingAgentsGraph(["market"], config=config, debug=True)
        print("✅ Graph initialization successful")
        return True, graph
    except Exception as e:
        print(f"❌ Graph initialization failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False, None

def test_simple_analysis():
    """Test simple analysis"""
    success, graph = test_graph_initialization()
    if not success:
        return False
    
    try:
        print("🚀 Start a simple analysis test...")
        # Perform simple analysis
        state, decision = graph.propagate("AAPL", "2025-06-27")
        print("✅ Analysis completed")
        print(f"decision making: {decision}")
        return True
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Main test function"""
    print("🧪 TradingAgents Functional testing")
    print("=" * 50)
    
    # Test basic import
    print("\n1. Test basic import...")
    if not test_basic_imports():
        return
    
    # Test environment variables
    print("\n2. Test environment variables...")
    if not test_environment_variables():
        print("❌ Environment variables are not configured correctly")
        return
    
    # Test chart initialization
    print("\n3. Test chart initialization...")
    success, graph = test_graph_initialization()
    if not success:
        return
    
    # Test simple analysis
    print("\n4. Test simple analysis...")
    if test_simple_analysis():
        print("\n🎉 All tests passed!")
    else:
        print("\n❌ Analysis test failed")

if __name__ == "__main__":
    main()
