#!/usr/bin/env python3
"""
Run a complete stock analysis and observe detailed logs of DeepSeek cost calculations
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

def test_full_stock_analysis():
    """Run a complete stock analysis"""
    print("🔬 Complete Stock Analysis - DeepSeek Cost Calculation Debugging")
    print("=" * 80)
    
    # Check API key
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY not found, unable to test")
        return False
    
    try:
        from tradingagents.graph.setup import TradingAgentsGraph
        from tradingagents.default_config import DEFAULT_CONFIG
        
        print("🔧 Initialize transaction analysis chart...")
        
        # Configuration DeepSeek
        config = DEFAULT_CONFIG.copy()
        config.update({
            "llm_provider": "deepseek",
            "deep_think_llm": "deepseek-chat",
            "quick_think_llm": "deepseek-chat",
            "max_debate_rounds": 1,  # Reduce rounds and save time
            "max_risk_discuss_rounds": 1,
            "online_tools": True,
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
            "company_of_interest": "300059",  # Oriental Fortune
            "trade_date": "2025-07-08"
        }
        
        print(f"\n📊 Start analyzing stocks: {input_data['company_of_interest']}")
        print(f"📅 transaction date: {input_data['trade_date']}")
        print("\n" + "="*100)
        print("To start the complete analysis process, please observe the detailed log of DeepSeek cost calculation:")
        print("="*100)
        
        # Run analysis
        result = graph.run(input_data)
        
        print("="*100)
        print("Analysis completed!")
        print("="*100)
        
        # Summary of output results
        if result and "decision" in result:
            decision = result["decision"]
            print(f"\n📋 Summary of analysis results:")
            print(f"   investment advice: {decision.get('action', 'N/A')}")
            print(f"   Confidence: {decision.get('confidence', 'N/A')}")
            print(f"   target price: {decision.get('target_price', 'N/A')}")
            
            if "market_report" in result:
                market_report = result["market_report"]
                print(f"   Market report length: {len(market_report)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Full analysis test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """main function"""
    print("🔬 Complete Stock Analysis - DeepSeek Cost Calculation Debug Test")
    print("=" * 80)
    print("📝 This test will run the complete stock analysis process")
    print("📝 Please carefully observe all costing logs")
    print("📝 Pay special attention to whether there are costs for¥0.000000 situation")
    print("=" * 80)
    
    success = test_full_stock_analysis()
    
    if success:
        print("\n🎉 Complete analysis test completed!")
        print("Please view the detailed log above to analyze the complete process of cost calculation.")
    else:
        print("\n❌ Full analysis test failed")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
