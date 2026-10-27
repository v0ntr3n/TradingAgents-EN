"""
Test whether fundamental analysts will call the tool repeatedly
"""
import os
import sys
from datetime import datetime

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_fundamentals_analyst():
    """Test Fundamental Analyst"""
    print("=" * 80)
    print("Test Fundamental Analyst - Check if the tool is called repeatedly")
    print("=" * 80)
    
    # Import necessary modules
    from tradingagents.agents.trading_graph import create_trading_graph
    
    # Create transaction diagram
    print("\n1️⃣ Create transaction diagram...")
    graph = create_trading_graph()
    
    # Prepare test input
    test_ticker = "000001"  # Ping An Bank
    test_date = datetime.now().strftime("%Y-%m-%d")
    
    print(f"\n2️⃣ test stocks: {test_ticker}")
    print(f"   Test date: {test_date}")
    
    # Perform fundamental analysis
    print("\n3️⃣ Start performing fundamental analysis...")
    print("   Please review the logs to check the following key information:")
    print("   - Whether the tool was only called once")
    print("   - Does it appear 'Skip repeated calls' log")
    print("   - Is the total time spent on tool calls reduced?")
    print("-" * 80)
    
    try:
        result = graph.invoke({
            "company_of_interest": test_ticker,
            "trade_date": test_date,
            "messages": [],
            "fundamentals_report": "",
            "technical_report": "",
            "news_report": "",
            "bull_report": "",
            "bear_report": "",
            "manager_report": "",
            "final_report": ""
        })
        
        print("-" * 80)
        print("\n✅ Fundamental analysis complete!")
        
        # Check results
        if result.get("fundamentals_report"):
            report = result["fundamentals_report"]
            print(f"\n📊 Fundamental report length: {len(report)} character")
            print(f"\n📊 Report preview(first 500 characters):")
            print(report[:500])
            print("...")
        else:
            print("\n⚠️ Fundamentals report not generated")
        
        print("\n" + "=" * 80)
        print("Test completed! Please check the log file logs/tradingagents.log")
        print("Key checkpoints:")
        print("1. Search 'Tool call' - There should only be 1 tool call")
        print("2. Search 'Repeat call check' - Check whether the check logic is effective")
        print("3. Search 'Skip force tool call' - If it appears, the repair has taken effect.")
        print("4. Search 'Force call to unified tool' - If it appears twice, it means there is still a problem")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_fundamentals_analyst()

