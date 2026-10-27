#!/usr/bin/env python3
"""
Alibaba Bailian large model integration test script
Used to verify whether the Alibaba Bailian integration in TradingAgents is working properly
"""

import os
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load .env file
load_dotenv()

def test_import():
    """Test whether the import is normal"""
    print("🔍 test 1: Check module imports...")
    try:
        from tradingagents.llm_adapters import ChatDashScope
        print("✅ ChatDashScope Import successful")
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        print("✅ TradingAgentsGraph Import successful")
        
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_api_key():
    """Test API key configuration"""
    print("\n🔍 test 2: Check API key configuration...")
    
    dashscope_key = os.getenv('DASHSCOPE_API_KEY')
    finnhub_key = os.getenv('FINNHUB_API_KEY')
    
    if not dashscope_key:
        print("❌ DASHSCOPE_API_KEY environment variable not found")
        print("💡 Please set: set DASHSCOPE_API_KEY=your_api_key")
        return False
    else:
        print(f"✅ DASHSCOPE_API_KEY: {dashscope_key[:10]}...")
    
    if not finnhub_key:
        print("❌ FINNHUB_API_KEY environment variable not found")
        print("💡 Please set: set FINNHUB_API_KEY=your_api_key")
        return False
    else:
        print(f"✅ FINNHUB_API_KEY: {finnhub_key[:10]}...")
    
    return True

def test_dashscope_connection():
    """Test Alibaba Bailian connection"""
    print("\n🔍 test 3: Check Ali Bailian connection...")
    
    try:
        import dashscope
        from dashscope import Generation
        
        # Set API key
        dashscope.api_key = os.getenv('DASHSCOPE_API_KEY')
        
        # Test simple calls
        response = Generation.call(
            model="qwen-turbo",
            messages=[{"role": "user", "content": "Hello, please reply'Connection successful'"}],
            result_format="message"
        )
        
        if response.status_code == 200:
            content = response.output.choices[0].message.content
            print(f"✅ Alibaba Bailian connection successful: {content}")
            return True
        else:
            print(f"❌ Alibaba Bailian connection failed: {response.code} - {response.message}")
            return False
            
    except Exception as e:
        print(f"❌ Alibaba Bailian connection test failed: {e}")
        return False

def test_langchain_adapter():
    """Test the LangChain adapter"""
    print("\n🔍 test 4: Check LangChain adapter...")
    
    try:
        from tradingagents.llm_adapters import ChatDashScope
        from langchain_core.messages import HumanMessage
        
        # Create adapter instance
        llm = ChatDashScope(model="qwen-turbo")
        
        # test call
        messages = [HumanMessage(content="please reply'Adapter works fine'")]
        response = llm.invoke(messages)
        
        print(f"✅ LangChain Adapter works fine: {response.content}")
        return True
        
    except Exception as e:
        print(f"❌ LangChain Adapter test failed: {e}")
        return False

def test_trading_graph_config():
    """Test TradingGraph configuration"""
    print("\n🔍 test 5: Check TradingGraph configuration...")
    
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create Alibaba Bailian configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "dashscope"
        config["deep_think_llm"] = "qwen-plus"
        config["quick_think_llm"] = "qwen-turbo"
        
        # Attempt to initialize (do not run analysis)
        ta = TradingAgentsGraph(debug=False, config=config)
        
        print("✅ TradingGraph Configuration successful")
        print(f"   deep thinking model: {config['deep_think_llm']}")
        print(f"   quick thinking model: {config['quick_think_llm']}")
        return True
        
    except Exception as e:
        print(f"❌ TradingGraph Configuration failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Alibaba Bailian large model integration test")
    print("=" * 50)
    
    tests = [
        test_import,
        test_api_key,
        test_dashscope_connection,
        test_langchain_adapter,
        test_trading_graph_config,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test exception: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Alibaba Bailian integration works normally")
        print("\n💡 Next step:")
        print("   1. Run python demo_dashscope.py for complete testing")
        print("   2. Or use python -m cli.main analyze to start interactive analysis")
    else:
        print("⚠️  Some tests failed, please check the configuration")
        print("\n🔧 Troubleshooting:")
        print("   1. Confirm installed dashscope: pip install dashscope")
        print("   2. Check if the API key is set correctly")
        print("   3. Confirm that the network connection is normal")
        print("   4. View detailed error information")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
