#!/usr/bin/env python3
"""
DeepSeek V3 Integration testing
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv(project_root / ".env", override=True)

def test_deepseek_availability():
    """Testing DeepSeek usability"""
    print("🔍 Testing DeepSeek V3 usability...")
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    enabled = os.getenv("DEEPSEEK_ENABLED", "false").lower() == "true"
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    
    print(f"API Key: {'✅ Already set' if api_key else '❌ not set'}")
    print(f"Base URL: {base_url}")
    print(f"Enabled status: {'✅ Enabled' if enabled else '❌ Not enabled'}")
    
    if not api_key:
        print("\n⚠️ Please set it in the .env file DEEPSEEK_API_KEY")
        print("📝 Get address: https://platform.deepseek.com/")
        print("💡 Note: You need to register and create a DeepSeek account API Key")
        return False
    
    if not enabled:
        print("\n⚠️ Please set it in the .env file DEEPSEEK_ENABLED=true")
        return False
    
    return True

def test_deepseek_adapter():
    """Test the DeepSeek adapter"""
    print("\n🧪 Test the DeepSeek adapter...")
    
    try:
        from tradingagents.llm.deepseek_adapter import DeepSeekAdapter, create_deepseek_adapter
        
        # Test adapter creation
        adapter = create_deepseek_adapter(model="deepseek-chat")
        print("✅ Adapter created successfully")
        
        # Test model information
        model_info = adapter.get_model_info()
        print(f"✅ Model information: {model_info['provider']} - {model_info['model']}")
        print(f"✅ context length: {model_info['context_length']}")
        
        # List of available models for testing
        models = DeepSeekAdapter.get_available_models()
        print(f"✅ Available models: {list(models.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Adapter test failed: {e}")
        return False

def test_deepseek_connection():
    """Test DeepSeek connection"""
    print("\n🔗 Test DeepSeek connection...")
    
    try:
        from tradingagents.llm.deepseek_adapter import create_deepseek_adapter
        from langchain.schema import HumanMessage
        
        # Create adapter
        adapter = create_deepseek_adapter(model="deepseek-chat")
        
        # Test a simple conversation
        messages = [HumanMessage(content="Hello, please briefly introduce the basic concepts of stock investment, within 50 words.")]
        response = adapter.chat(messages)
        print(f"✅ model response: {response[:100]}...")
        
        # test connection
        connection_ok = adapter.test_connection()
        print(f"✅ Connection test: {'success' if connection_ok else 'failed'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        return False

def test_deepseek_tools():
    """Test DeepSeek tool calls"""
    print("\n🛠️ Test tool call function...")
    
    try:
        from langchain.tools import tool
        from tradingagents.llm.deepseek_adapter import create_deepseek_adapter
        
        # Define testing tools
        @tool
        def get_stock_price(symbol: str) -> str:
            """Get stock price"""
            return f"stocks{symbol}The current price of is$150.00"
        
        @tool
        def get_market_news(symbol: str) -> str:
            """Get market news"""
            return f"stocks{symbol}The latest news: Company performance is good, analysts are optimistic about the prospects"
        
        # Create adapter
        adapter = create_deepseek_adapter(model="deepseek-chat")
        
        # Create an agent
        tools = [get_stock_price, get_market_news]
        system_prompt = "You are a professional stock analysis assistant who can use tools to obtain stock information and perform analysis. Please answer in Chinese."
        
        agent = adapter.create_agent(tools, system_prompt, verbose=True)
        print("✅ Agent created successfully")
        
        # Test tool call
        result = agent.invoke({"input": "Please help me check the stock price and latest news of AAPL"})
        print(f"✅ Tool call successful: {result['output'][:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool call test failed: {e}")
        return False

def test_deepseek_trading_graph():
    """Testing DeepSeek integration in transaction graph"""
    print("\n📊 Testing the Trading Graph Integration...")
    
    try:
        from tradingagents.default_config import DEFAULT_CONFIG
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        
        # Create DeepSeek configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "deepseek"
        config["deep_think_llm"] = "deepseek-chat"
        config["quick_think_llm"] = "deepseek-chat"
        config["max_debate_rounds"] = 1  # Reduce testing time
        config["online_tools"] = False   # Disable online tools to speed up testing
        
        # Create transaction diagram
        ta = TradingAgentsGraph(debug=True, config=config)
        print("✅ Trading chart created successfully")
        
        # Note: No actual analysis is performed here, only initialization is tested.
        print("✅ DeepSeek Integrated into trading graph successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Transaction graph integration test failed: {e}")
        return False

def test_deepseek_models():
    """Test different DeepSeek models"""
    print("\n🎯 Test different DeepSeek models...")
    
    try:
        from tradingagents.llm.deepseek_adapter import create_deepseek_adapter
        
        models_to_test = ["deepseek-chat"]  # Only test models that are best suited for stock analysis
        
        for model in models_to_test:
            try:
                adapter = create_deepseek_adapter(model=model)
                info = adapter.get_model_info()
                print(f"✅ {model}: {info['context_length']} context")
            except Exception as e:
                print(f"⚠️ {model}: test failed - {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ Model test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🎯 DeepSeek V3 Integration testing")
    print("=" * 50)
    
    tests = [
        ("Availability check", test_deepseek_availability),
        ("Adapter test", test_deepseek_adapter),
        ("Connection test", test_deepseek_connection),
        ("Tool call", test_deepseek_tools),
        ("Transaction graph integration", test_deepseek_trading_graph),
        ("Model testing", test_deepseek_models),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n{'='*20} {test_name} {'='*20}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary results
    print("\n" + "="*50)
    print("📋 Summary of test results:")
    print("="*50)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n total: {passed}/{len(results)} tests passed")
    
    if passed == len(results):
        print("\n🎉 All tests passed! DeepSeek V3 integration successful!")
        print("\n📝 Next step:")
        print("1. Configure your DeepSeek API key in the .env file")
        print("2. settings DEEPSEEK_ENABLED=true enable DeepSeek")
        print("3. Select a DeepSeek model in the web interface or CLI")
        print("4. Enjoy cost-effective AI analysis services")
    else:
        print(f"\n⚠️ {len(results) - passed} Test failed, please check configuration and dependencies")
    
    return passed == len(results)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
