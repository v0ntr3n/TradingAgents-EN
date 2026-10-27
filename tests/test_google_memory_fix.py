#!/usr/bin/env python3
"""
Testing fixed Google AI memory capabilities
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

def test_google_memory_fixed():
    """Testing fixed Google AI memory capabilities"""
    try:
        print("🧪 Testing fixed Google AI memory capabilities")
        print("=" * 60)
        
        from tradingagents.agents.utils.memory import FinancialSituationMemory
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Check API key
        google_key = os.getenv('GOOGLE_API_KEY')
        dashscope_key = os.getenv('DASHSCOPE_API_KEY')
        
        print(f"🔑 API Key status:")
        print(f"   Google API: {'✅ configured' if google_key else '❌ Not configured'}")
        print(f"   Ali Bailian API: {'✅ configured' if dashscope_key else '❌ Not configured'}")
        
        if not google_key:
            print("❌ Google API Key is not configured and cannot be tested")
            return False
        
        # Create a Google AI configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        
        print("\n📊 Create a Google AI in-memory instance...")
        memory = FinancialSituationMemory("test_google_memory", config)
        
        print(f"✅ Memory instance created successfully")
        print(f"   LLM provider: {memory.llm_provider}")
        print(f"   embedded model: {memory.embedding}")
        print(f"   client type: {type(memory.client)}")
        
        # Test embed functionality
        print("\n📝 Test embed functionality...")
        test_text = "Analysis of the investment value of Apple stock in a high inflation environment"
        
        try:
            embedding = memory.get_embedding(test_text)
            print(f"✅ Embedding generated successfully")
            print(f"   embedded dimensions: {len(embedding)}")
            print(f"   Embed preview: {embedding[:5]}...")
            
            # test memory storage
            print("\n💾 test memory storage...")
            memory.add_situations([
                ("High inflation environment, rising interest rates, technology stocks under pressure", "It is recommended to pay attention to large technology companies with stable cash flow, such as Apple, Microsoft, etc."),
                ("Market volatility intensifies, investor sentiment cautious", "It is recommended to diversify investments and focus on defensive sectors")
            ])
            print("✅ Memory storage successful")
            
            # Test memory retrieval
            print("\n🔍 Test memory retrieval...")
            similar_memories = memory.get_memories("Tech stock investing during times of rising inflation", n_matches=2)
            print(f"✅ Memory retrieval successful")
            print(f"   retrieved {len(similar_memories)} related memories")

            for i, mem in enumerate(similar_memories, 1):
                situation = mem['matched_situation']
                recommendation = mem['recommendation']
                score = mem['similarity_score']
                print(f"   memory{i} (Similarity: {score:.3f}):")
                print(f"     situation: {situation}")
                print(f"     Suggestions: {recommendation}")
            
            return True
            
        except Exception as e:
            print(f"❌ Embed functionality test failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Google AI Memory test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_google_tradingagents_with_memory():
    """Test with memory Google AI TradingAgents"""
    try:
        print("\n🧪 Test with memory Google AI TradingAgents")
        print("=" * 60)
        
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Check API key
        google_key = os.getenv('GOOGLE_API_KEY')
        dashscope_key = os.getenv('DASHSCOPE_API_KEY')
        
        if not google_key:
            print("❌ Google API Key not configured")
            return False
        
        if not dashscope_key:
            print("⚠️ Alibaba Bailian API key is not configured, and the memory function may not be available")
        
        # Create configuration
        config = DEFAULT_CONFIG.copy()
        config["llm_provider"] = "google"
        config["deep_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
        config["quick_think_llm"] = "gemini-2.5-flash-lite-preview-06-17"
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
        print(f"   LLM provider: {config['llm_provider']}")
        print(f"   model: {config['deep_think_llm']}")
        print(f"   memory function: {config['memory_enabled']}")
        
        # Create TradingAgentsGraph instance
        print("🚀 Initialize the TradingAgents graph with memory...")
        graph = TradingAgentsGraph(["market"], config=config, debug=False)
        
        print("✅ TradingAgents Graph initialization successful")
        
        # Test analysis
        print("📊 Start stock analysis with memory...")
        
        try:
            state, decision = graph.propagate("AAPL", "2025-06-27")
            
            if state and decision:
                print("✅ Gemini stock analysis with memory is successful!")
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
            print(f"❌ Stock analysis with memory fails: {e}")
            import traceback
            print(traceback.format_exc())
            return False
            
    except Exception as e:
        print(f"❌ TradingAgents test with memory fails: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 Google AI Memory function repair test")
    print("=" * 70)
    
    # Run tests
    results = {}
    
    results['memory function'] = test_google_memory_fixed()
    results['complete TradingAgents'] = test_google_tradingagents_with_memory()
    
    # Summary results
    print(f"\n📊 Summary of test results:")
    print("=" * 50)
    
    for test_name, success in results.items():
        status = "✅ Pass" if success else "❌ failed"
        print(f"  {test_name}: {status}")
    
    successful_tests = sum(results.values())
    total_tests = len(results)
    
    print(f"\n🎯 Overall results: {successful_tests}/{total_tests} Test passed")
    
    if successful_tests == total_tests:
        print("🎉 Google AI The memory function was repaired successfully!")
        print("\n💡 Features available now:")
        print("   ✅ Google Gemini as main LLM")
        print("   ✅ Alibaba Bailian as an embedded service")
        print("   ✅ Complete memory and learning capabilities")
        print("   ✅ Chinese Analysis and Reasoning")
        print("   ✅ Historical experience learning")
    elif successful_tests > 0:
        print("⚠️ Some features are available")
        if results['memory function'] and not results['complete TradingAgents']:
            print("💡 The memory functions fine, but there are other issues with the complete process")
    else:
        print("❌ Repair failed, please check API key configuration")

if __name__ == "__main__":
    main()
