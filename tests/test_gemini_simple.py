#!/usr/bin/env python3
"""
Simplified Gemini testing (memory features disabled)
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

def test_gemini_simple_analysis():
    """Test Gemini s simple analysis capabilities"""
    try:
        print("🧪 Test Gemini simple analysis function")
        print("=" * 60)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Check API key
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            print("❌ Google API Key not configured")
            return False
        
        print(f"✅ Google API Key configured: {google_api_key[:20]}...")
        
        # Create a simplified configuration (disable memory and online tools)
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        config["quick_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        config["online_tools"] = False  # Disable online tools to avoid API restrictions
        config["memory_enabled"] = False  # Disable memory to avoid OpenAI dependencies
        config["max_debate_rounds"] = 1  # Reduce rounds
        config["max_risk_discuss_rounds"] = 1
        
        # repair path
        config["data_dir"] = str(project_root / "data")
        config["results_dir"] = str(project_root / "results")
        config["data_cache_dir"] = str(project_root / "tradingagents" / "dataflows" / "data_cache")
        
        # Create directory
        os.makedirs(config["data_dir"], exist_ok=True)
        os.makedirs(config["results_dir"], exist_ok=True)
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        print("✅ Simplified configuration created successfully")
        print(f"   LLM provider: {config['llm_provider']}")
        print(f"   model: {config['deep_think_llm']}")
        print(f"   Online tools: {config['online_tools']}")
        print(f"   memory function: {config['memory_enabled']}")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize TradingAgents graph...")
        graph = TradingAgentsGraph(["market"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        
        # Test simple analysis
        print("📊 Start Simplifying Stock Analysis...")
        print("   Use offline data to avoid API restrictions...")
        
        try:
            state, decision = graph.propagate("AAPL", "2025-06-27")
            
            if state and decision:
                print("✅ Gemini Driven stock analysis successfully completed!")
                print(f"   final decision: {decision}")
                
                # Check market reports
                if "market_report" in state and state["market_report"]:
                    market_report = state["market_report"]
                    print(f"   Market report length: {len(market_report)} character")
                    print(f"   Report preview: {market_report[:200]}...")
                
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
        print(f"❌ Simplified test failure: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_gemini_analyst_direct():
    """Test Gemini Analyst Directly"""
    try:
        print("\n🧪 Test Gemini Analyst Directly")
        print("=" * 60)
        
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from langchain_google_genai import ChatGoogleGenerativeAI
        from tradingagents.default_config import DEFAULT_CONFIG
        from langchain_core.messages import HumanMessage
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = False
        
        # Create Gemini LLM
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite-preview-06-17",
            temperature=0.1,
            max_tokens=1000,
            google_api_key=os.getenv('GOOGLE_API_KEY')
        )
        
        # Create toolkit
        toolkit = Toolkit(config=config)
        
        print("✅ Component created successfully")
        
        # Create a market analyst
        market_analyst = create_market_analyst(llm, toolkit)
        
        print("✅ Market analyst created successfully")
        
        # Create test state
        test_state = {
            "messages": [HumanMessage(content="Analyzing AAPL s Market Technical Indicators")],
            "company_of_interest": "AAPL",
            "trade_date": "2025-06-27"
        }
        
        print("📊 Start market analysis...")
        
        # Perform analysis
        result = market_analyst(test_state)
        
        if result and "market_report" in result:
            market_report = result["market_report"]
            if market_report and len(market_report) > 100:
                print("✅ Market analysis successfully completed")
                print(f"   Report length: {len(market_report)} character")
                print(f"   Report preview: {market_report[:200]}...")
                return True
            else:
                print("⚠️ The market analysis is completed but the report content is less")
                return True
        else:
            print("⚠️ Market analysis completed but no report generated")
            return False
            
    except Exception as e:
        print(f"❌ Direct analyst testing failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def main():
    """Main test function"""
    print("🧪 Gemini Simplify integration testing")
    print("=" * 70)
    
    # Check environment variables
    google_api_key = os.getenv('GOOGLE_API_KEY')
    if not google_api_key:
        print("❌ Google API Key not configured")
        print("💡 Please set it in the .env file GOOGLE_API_KEY")
        return
    
    # Run tests
    results = {}
    
    print("Step 1: direct analyst testing")
    print("-" * 30)
    results['direct analyst'] = test_gemini_analyst_direct()
    
    print("\n Step 2: Simplifying TradingAgents testing")
    print("-" * 30)
    results['Simplify TradingAgents'] = test_gemini_simple_analysis()
    
    # Summary results
    print(f"\n📊 Simplified test results summary:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")
    
    if successful_tests == total_tests:
        print("🎉 Gemini The core functions of the model are fully available!")
        print("\n💡 Usage suggestions:")
        print("   1. Gemini Basic functions work normally")
        print("   2. Can be used in TradingAgents Gemini")
        print("   3. It is recommended to disable the memory function to avoid OpenAI dependency")
        print("   4. Can use offline mode to avoid API restrictions")
        print("   5. Support Chinese analysis and reasoning")
    elif successful_tests > 0:
        print("⚠️ Gemini Some features are available")
        print("💡 The core functions are normal and basic analysis can be performed")
    else:
        print("❌ Gemini Model not available")
        print("💡 Please check API key and network connection")

if __name__ == "__main__":
    main()
