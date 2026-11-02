#!/usr/bin/env python3
"""
Final test of fixed Gemini integration
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

def test_gemini_tradingagents():
    """Testing the fixed Gemini integration with TradingAgents"""
    try:
        print("🧪 Testing the fixed Gemini integration with TradingAgents")
        print("=" * 60)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Check API key
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            print("❌ Google API Key not configured")
            return False
        
        print(f"✅ Google API Key configured: {google_api_key[:20]}...")
        
        # Create a configuration using Gemini
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        config["quick_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        config["online_tools"] = True
        config["memory_enabled"] = True
        
        # repair path
        config["data_dir"] = str(project_root / "data")
        config["results_dir"] = str(project_root / "results")
        config["data_cache_dir"] = str(project_root / "tradingagents" / "dataflows" / "data_cache")
        
        # Create directory
        os.makedirs(config["data_dir"], exist_ok=True)
        os.makedirs(config["results_dir"], exist_ok=True)
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        print("✅ Configuration created successfully")
        print(f"   LLM provider: {config['llm_provider']}")
        print(f"   deep thinking model: {config['deep_think_llm']}")
        print(f"   quick thinking model: {config['quick_think_llm']}")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize TradingAgents graph...")
        graph = TradingAgentsGraph(["market"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        
        # Test simple analysis
        print("📊 Start stock analysis...")
        print("   This may take a few minutes...")
        
        try:
            state, decision = graph.propagate("AAPL", "2025-06-27")
            
            if state and decision:
                print("✅ Gemini Driven stock analysis successfully completed!")
                print(f"   final decision: {decision}")
                
                # Check various reports
                reports = ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
                for report_name in reports:
                    if report_name in state and state[report_name]:
                        report_content = state[report_name]
                        print(f"   {report_name}: {len(report_content)} character")
                        print(f"   Preview: {report_content[:100]}...")
                        print()
                
                return True
            else:
                print("❌ Analysis completed but result is empty")
                return False
                
        except Exception as e:
            print(f"❌ Stock analysis failed: {e}")
            import traceback
            print(traceback.format_exc())
            return False
            
    except Exception as e:
        print(f"❌ TradingAgents Integration test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_gemini_basic():
    """Basic Gemini functional testing"""
    try:
        print("🧪 Basic Gemini functional testing")
        print("=" * 50)
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Create LangChain Gemini instance
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite-preview-06-17",
            temperature=0.1,
            max_tokens=500,
            google_api_key=os.getenv('GOOGLE_API_KEY')
        )
        
        print("✅ Gemini Instance created successfully")
        
        # Test Chinese conversation
        print("📝 Test Chinese conversation...")
        response = llm.invoke("Please analyze the current development trends of artificial intelligence technology in Chinese")
        
        if response and response.content:
            print("✅ Chinese conversation test successful")
            print(f"   response length: {len(response.content)} character")
            print(f"   Response preview: {response.content[:200]}...")
            return True
        else:
            print("❌ Chinese conversation test failed")
            return False
            
    except Exception as e:
        print(f"❌ Basic functional test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Gemini final integration test")
    print("=" * 70)
    
    # Check environment variables
    google_api_key = os.getenv('GOOGLE_API_KEY')
    if not google_api_key:
        print("❌ Google API Key not configured")
        print("💡 Please set it in the .env file GOOGLE_API_KEY")
        return
    
    # Run tests
    results = {}
    
    print("Step 1: Basic functional testing")
    print("-" * 30)
    results['Basic functions'] = test_gemini_basic()
    
    print("\n Step 2: TradingAgents Integration testing")
    print("-" * 30)
    results['TradingAgents Integrate'] = test_gemini_tradingagents()
    
    # Summary results
    print(f"\n📊 Summary of final test results:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")
    
    if successful_tests == total_tests:
        print("🎉 Gemini The model is fully integrated successfully!")
        print("\n💡 Usage suggestions:")
        print("   1. Select in the web interface'Google'As an LLM provider")
        print("   2. Use model name: gemini-2.0-flash")
        print("   3. Complete Chinese stock analysis is available")
        print("   4. Supports all analyst types")
        print("   5. Gemini Excellent performance in multilingual and reasoning skills")
    elif successful_tests > 0:
        print("⚠️ Gemini Some features are available")
        if results['Basic functions'] and not results['TradingAgents Integrate']:
            print("💡 The basic functions are normal, but there is a problem with the TradingAgents integration")
            print("   It is recommended to check the configuration and dependencies")
    else:
        print("❌ Gemini Model not available")
        print("💡 Please check API key, network connection and dependency installation")

if __name__ == "__main__":
    main()
