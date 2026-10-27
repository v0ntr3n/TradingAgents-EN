#!/usr/bin/env python3
"""
Test map routing fix
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_graph_routing():
    """Test whether graph routing is working properly"""
    print("🔬 Test map routing fix")
    print("=" * 60)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.graph.setup import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        print("🔧 Create transaction analysis chart...")
        
        # Configuration DeepSeek
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-chat",
            "quick_think_llm": "deepseek-chat",
            "max_debate_rounds": 1,  # Reduce rounds and test quickly
            "max_risk_discuss_rounds": 1,
            "online_tools": False,  # Close online tools and reduce complexity
            "memory_enabled": False
        })
        
        print(f"📊 Configuration information:")
        print(f"   LLM provider: {config['llm_provider']}")
        print(f"   deep thinking model: {config['deep_think_llm']}")
        print(f"   quick thinking model: {config['quick_think_llm']}")
        
        # Create graph instance
        graph = TradingAgentsGraph(config)
        
        # Set analysts (select only market analysts to reduce complexity)
        print(f"📈 Set up analysts...")
        graph.setup_and_compile(selected_analysts=["market"])
        
        print(f"✅ Picture setting completed")
        
        # ready to enter
        input_data = {
            "company_of_interest": "AAPL",  # Use US stocks to reduce complexity
            "trade_date": "2025-07-08"
        }
        
        print(f"\n📊 Start test analysis: {input_data['company_of_interest']}")
        print(f"📅 transaction date: {input_data['trade_date']}")
        print("\n" + "="*60)
        print("Start the graph routing test and observe whether there is KeyError...")
        print("="*60)
        
        # Run analysis
        result = graph.run(input_data)
        
        print("="*60)
        print("Graph routing test completed!")
        print("="*60)
        
        # Summary of output results
        if result and "decision" in result:
            decision = result["decision"]
            print(f"\n📋 Summary of analysis results:")
            print(f"   investment advice: {decision.get('action', 'N/A')}")
            print(f"   Confidence: {decision.get('confidence', 'N/A')}")
            print(f"   target price: {decision.get('target_price', 'N/A')}")
            
            return True
        else:
            print("❌ No valid analysis results were obtained")
            return False
        
    except KeyError as e:
        print(f"❌ graph routing KeyError: {e}")
        print("   This indicates that there is still an issue with the node name mapping")
        return False
    except Exception as e:
        print(f"❌ Other errors: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Graph routing repair test")
    print("=" * 80)
    print("📝 This test will verify that graph routing is working properly")
    print("📝 Mainly check whether there are still KeyError: 'Bull Researcher'Error")
    print("=" * 80)
    
    success = test_graph_routing()
    
    if success:
        print("\n🎉 The graph routing test was successful!")
        print("   KeyError Problem fixed")
    else:
        print("\n❌ Graph routing test failed")
        print("   Need further debugging")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
