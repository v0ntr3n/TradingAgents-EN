#!/usr/bin/env python3
"""
Final verification of the recommended Gemini model
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

def test_recommended_model():
    """Test the recommended gemini-2.0-flash model"""
    try:
        print("🧪 Final verification of recommended model: gemini-2.0-flash")
        print("=" * 60)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Check API key
        google_key = os.getenv('GOOGLE_API_KEY')
        dashscope_key = os.getenv('DASHSCOPE_API_KEY')
        
        print(f"🔑 API Key status:")
        print(f"   Google API: {'✅ configured' if google_key else '❌ Not configured'}")
        print(f"   Ali Bailian API: {'✅ configured' if dashscope_key else '❌ Not configured'}")
        
        if not google_key:
            print("❌ Google API Key not configured")
            return False
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.0-flash"
        config["quick_think_llm"] = "gemini-2.0-flash"
        config["online_tools"] = False  # Avoid API restrictions
        config["memory_enabled"] = True  # Enable memory features
        config["max_debate_rounds"] = 2  # Increase debate rounds
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
        print(f"   model: {config['deep_think_llm']}")
        print(f"   memory function: {config['memory_enabled']}")
        print(f"   debate rounds: {config['max_debate_rounds']}")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize TradingAgents graph...")
        graph = TradingAgentsGraph(["market", "fundamentals"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        print("   analyst: market analyst + fundamental analyst")
        
        # Test analysis
        print("📊 Start a complete stock analysis...")
        print("   Use gemini-2.0-flash + Alibaba Bailian embedded")
        print("   This may take a few minutes...")
        
        try:
            state, decision = graph.propagate("AAPL", "2025-06-27")
            
            if state and decision:
                print("✅ gemini-2.0-flash Complete analysis of the driver successful!")
                print(f"   final decision: {decision}")
                
                # Check various reports
                reports = {
                    "market_report": "Market technical analysis",
                    "fundamentals_report": "fundamental analysis", 
                    "sentiment_report": "sentiment analysis",
                    "news_report": "news analysis"
                }
                
                for report_key, report_name in reports.items():
                    if report_key in state and state[report_key]:
                        report_content = state[report_key]
                        print(f"   {report_name}: {len(report_content)} character")
                        if len(report_content) > 100:
                            print(f"     Preview: {report_content[:150]}...")
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
        print(f"❌ Final verification failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def compare_models():
    """Recommendations for comparing different models"""
    print("\n📊 Model selection recommendations")
    print("=" * 60)
    
    models_comparison = {
        "gemini-2.5-pro": {
            "Status": "❌ LangChain Integration issues",
            "Advantages": "The latest version with the strongest theoretical performance",
            "Disadvantages": "LangChain Integration is unstable",
            "Recommended": "Not recommended (integration issues)"
        },
        "gemini-2.5-flash": {
            "Status": "❌ LangChain Integration issues", 
            "Advantages": "Latest version, fast",
            "Disadvantages": "LangChain Integration is unstable",
            "Recommended": "Not recommended (integration issues)"
        },
        "gemini-2.0-flash": {
            "Status": "✅ fully available",
            "Advantages": "New version, LangChain is stable and has excellent performance",
            "Disadvantages": "Not the latest version 2.5",
            "Recommended": "🏆 Highly recommended"
        },
        "gemini-1.5-pro": {
            "Status": "✅ fully available",
            "Advantages": "Stable and powerful",
            "Disadvantages": "Older version",
            "Recommended": "Alternatives"
        }
    }
    
    for model, info in models_comparison.items():
        print(f"\n🤖 {model}:")
        for key, value in info.items():
            print(f"   {key}: {value}")

def main():
    """main function"""
    print("🧪 Gemini Model final verification")
    print("=" * 70)
    
    # Run final verification
    success = test_recommended_model()
    
    # Show comparison
    compare_models()
    
    # Final recommendations
    print(f"\n📊 Final test results:")
    print("=" * 50)
    
    if success:
        print("✅ gemini-2.0-flash Complete verification successful!")
        print("\n🎉 Final recommended configuration:")
        print("   LLM provider: Google")
        print("   Model name: gemini-2.0-flash")
        print("   Embed services: Ali Bailian (text-embedding-v3)")
        print("   memory function: enable")
        print("\n💡 Summary of advantages:")
        print("   🧠 Excellent reasoning skills")
        print("   🌍 Perfect Chinese support")
        print("   🔧 Stable LangChain integration")
        print("   💾 Complete memory learning function")
        print("   📊 Accurate financial analysis")
        print("\n🚀 You can now use this configuration in the web interface!")
    else:
        print("❌ Authentication failed")
        print("💡 It is recommended to use gemini-1.5-pro as an alternative")

if __name__ == "__main__":
    main()
