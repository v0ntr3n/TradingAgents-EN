#!/usr/bin/env python3
"""
Testing the Gemini 2.5 Pro model
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

def test_gemini_25_pro_basic():
    """Test the basic functions of Gemini 2.5 Pro"""
    try:
        print("🧪 Test the basic functions of Gemini 2.5 Pro")
        print("=" * 60)
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Check API key
        google_api_key = os.getenv('GOOGLE_API_KEY')
        if not google_api_key:
            print("❌ Google API Key not configured")
            return False
        
        print(f"✅ Google API Key configured: {google_api_key[:20]}...")
        
        # Create a Gemini 2.5 Pro instance
        print("🚀 Create a Gemini 2.5 Pro instance...")
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            max_tokens=1500,
            google_api_key=google_api_key
        )
        
        print("✅ Gemini 2.5 Pro Instance created successfully")
        
        # Test Chinese stock analysis
        print("📊 Test Chinese stock analysis...")
        response = llm.invoke("""
        Please analyze Apple in Chinese(AAPL)investment value. Please analyze from the following aspects:
        
        1. Company fundamental analysis
        2. Technological innovation capability
        3. competitive market position
        4. financial health
        5. Investment risk assessment
        6. investment advice
        
        Please provide detailed analysis and reasoning process.
        """)
        
        if response and response.content:
            print("✅ Chinese stock analysis successful")
            print(f"   response length: {len(response.content)} character")
            print(f"   Response preview: {response.content[:300]}...")
            return True
        else:
            print("❌ Chinese stock analysis failed")
            return False
            
    except Exception as e:
        print(f"❌ Gemini 2.5 Pro Basic test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_gemini_25_pro_tradingagents():
    """Testing Gemini 2.5 Pro for use with TradingAgents"""
    try:
        print("\n🧪 Testing Gemini 2.5 Pro for use with TradingAgents")
        print("=" * 60)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.5-pro"
        config["quick_think_llm"] = "gemini-2.5-pro"
        config["online_tools"] = False  # Avoid API restrictions
        config["memory_enabled"] = True  # Enable memory features
        config["max_debate_rounds"] = 1
        config["max_risk_discuss_rounds"] = 1
        
        # repair path
        config["data_dir"] = str(project_root / "data")
        config["results_dir"] = str(project_root / "results")
        config["data_cache_dir"] = str(project_root / "tradingagents" / "dataflows" / "data_cache")
        
        # Create directory
        os.makedirs(config["data_dir"], exist_ok=True)
        os.makedirs(config["results_dir"], exist_ok=True)
        os.makedirs(config["data_cache_dir"], exist_ok=True)
        
        print("✅ Configuration created successfully")
        print(f"   model: gemini-2.5-pro")
        print(f"   memory function: {config['memory_enabled']}")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize TradingAgents graph...")
        graph = TradingAgentsGraph(["market"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        
        # Test analysis
        print("📊 Start Gemini 2.5 Pro Stock Analysis...")
        print("   This may take a few minutes...")
        
        try:
            state, decision = graph.propagate("AAPL", "2025-06-27")
            
            if state and decision:
                print("✅ Gemini 2.5 Pro Drive stock analysis for success!")
                print(f"   final decision: {decision}")
                
                # Check various reports
                reports = ["market_report", "sentiment_report", "news_report", "fundamentals_report"]
                for report_name in reports:
                    if report_name in state and state[report_name]:
                        report_content = state[report_name]
                        print(f"   {report_name}: {len(report_content)} character")
                        if len(report_content) > 100:
                            print(f"   Preview: {report_content[:150]}...")
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
        print(f"❌ TradingAgents test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_gemini_25_pro_complex_reasoning():
    """Test the complex reasoning capabilities of Gemini 2.5 Pro"""
    try:
        print("\n🧪 Test the complex reasoning capabilities of Gemini 2.5 Pro")
        print("=" * 60)
        
        from langchain_google_genai import ChatGoogleGenerativeAI
        
        # Create instance
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-pro",
            temperature=0.1,
            max_tokens=2000,
            google_api_key=os.getenv('GOOGLE_API_KEY')
        )
        
        # complex reasoning test
        complex_prompt = """
        Please perform complex investment analysis reasoning:
        
        Scene setting:
        - Time: June 2025
        - Fed Policy: Just cut interest rates by 25 basis points
        - Inflation rate: 2.8%, trending downward
        - US-China relations: Trade tensions ease
        - AI Development: ChatGPT and other AI tools are rapidly gaining popularity
        - Geopolitics: The conflict between Russia and Ukraine continues, and the situation in the Middle East is tense
        
        Please analyze the investment value ranking of the following three stocks in this complex macro environment:
        1. apple inc.(AAPL) - consumer electronics+AI
        2. NVIDIA(NVDA) - AI chip leader
        3. Microsoft(MSFT) - cloud computing+AI Software
        
        Requirements:
        1. Analyze each stock s strengths and weaknesses in the current environment
        2. Consider the impact of macroeconomic factors on each stock
        3. Assess the long-term impact of AI developments on companies
        4. Provide investment prioritization and rationale
        5. Give specific investment advice and risk warnings
        
        Please provide a detailed logical reasoning process in Chinese.
        """
        
        print("🧠 Start complex reasoning test...")
        response = llm.invoke(complex_prompt)
        
        if response and response.content and len(response.content) > 800:
            print("✅ Complex reasoning test successful")
            print(f"   response length: {len(response.content)} character")
            print(f"   Response preview: {response.content[:400]}...")
            return True
        else:
            print("❌ Complex reasoning test failed: response too short or no content")
            return False
            
    except Exception as e:
        print(f"❌ Complex reasoning test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Gemini 2.5 Pro full test")
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
    results['Basic functions'] = test_gemini_25_pro_basic()
    
    print("\n Step 2: complex reasoning test")
    print("-" * 30)
    results['complex reasoning'] = test_gemini_25_pro_complex_reasoning()
    
    print("\n Step 3: TradingAgents Integration testing")
    print("-" * 30)
    results['TradingAgents Integrate'] = test_gemini_25_pro_tradingagents()
    
    # Summary results
    print(f"\n📊 Gemini 2.5 Pro Summary of test results:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")
    
    if successful_tests == total_tests:
        print("🎉 Gemini 2.5 Pro Totally available!")
        print("\n💡 Gemini 2.5 Pro Advantages:")
        print("   🧠 Stronger reasoning skills")
        print("   📊 Better complex analysis")
        print("   🌍 Excellent multi-language support")
        print("   💰 More accurate financial analysis")
        print("   🔍 deeper insights")
        print("\n🚀 Usage suggestions:")
        print("   1. Select in the web interface'Google'As an LLM provider")
        print("   2. Use model name: gemini-2.5-pro")
        print("   3. Suitable for complex investment analysis tasks")
        print("   4. Can handle multi-factor comprehensive analysis")
    elif successful_tests >= 2:
        print("⚠️ Gemini 2.5 Pro Most functions available")
        print("💡 Can be used for basic analysis, some advanced functions may need to be adjusted")
    else:
        print("❌ Gemini 2.5 Pro Not available")
        print("💡 Please check API key permissions and network connection")

if __name__ == "__main__":
    main()
