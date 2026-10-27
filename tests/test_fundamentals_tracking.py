#!/usr/bin/env python3
"""
Fundamental Analysis Stock Symbol Tracking Test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_fundamentals_analyst():
    """Testing Fundamental Analyst s Stock Symbol Handling"""
    print("\n🔍 Fundamental Analyst Stock Symbol Tracking Test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        # Create simulation state
        state = {
            "company_of_interest": test_ticker,
            "trade_date": "2025-07-15",
            "messages": []
        }
        
        print(f"\n🔧 Start calling fundamental analysts...")
        
        # Import fundamental analysts
        from tradingagents.agents.analysts.fundamentals_analyst import fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import AgentUtils
        
        # Create toolkit
        toolkit = AgentUtils()
        
        # Call a fundamental analyst
        result = fundamentals_analyst(state, toolkit)
        
        print(f"\n✅ Fundamental analyst call completed")
        print(f"📊 Return status type: {type(result)}")
        
        # Check the returned status
        if isinstance(result, dict):
            if 'fundamentals_report' in result:
                report = result['fundamentals_report']
                print(f"📄 Fundamental report length: {len(report) if report else 0}")
                
                # Check the stock symbol in the report
                if report:
                    print(f"\n🔍 Check the stock symbol in the report...")
                    if "002027" in report:
                        print("✅ Reports contain correct ticker symbols 002027")
                    else:
                        print("❌ Report does not contain correct ticker symbol 002027")
                        
                    if "002021" in report:
                        print("⚠️ Report contains incorrect stock symbol 002021")
                    else:
                        print("✅ Reports do not contain incorrect ticker symbols 002021")
                        
                    # Display the first 500 characters of the report
                    print(f"\n📄 Report first 500 characters:")
                    print("-" * 60)
                    print(report[:500])
                    print("-" * 60)
            else:
                print("❌ None in return status fundamentals_report")
        else:
            print(f"❌ The return result type is incorrect: {type(result)}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_unified_tool_direct():
    """Direct testing of unified fundamental tools"""
    print("\n🔧 Direct testing of unified fundamental tools")
    print("=" * 80)
    
    test_ticker = "002027"
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger.setLevel("INFO")
        
        # Import toolkit
        from tradingagents.agents.utils.agent_utils import AgentUtils
        
        # Create toolkit instance
        toolkit = AgentUtils()
        
        print(f"\n🔧 Call the Unified Fundamentals Tool...")
        
        # Directly call unified fundamental tools
        result = toolkit.get_stock_fundamentals_unified.invoke({
            'ticker': test_ticker,
            'start_date': '2025-06-01',
            'end_date': '2025-07-15',
            'curr_date': '2025-07-15'
        })
        
        print(f"\n✅ Unified fundamental tool call completed")
        print(f"📊 Return result length: {len(result) if result else 0}")
        
        # Check the stock symbol in the results
        if result:
            print(f"\n🔍 Check the stock symbol in the results...")
            if "002027" in result:
                print("✅ The results contain the correct ticker symbol 002027")
            else:
                print("❌ Results do not contain the correct stock symbol 002027")
                
            if "002021" in result:
                print("⚠️ Results contain wrong stock symbol 002021")
            else:
                print("✅ Results do not contain incorrect stock symbols 002021")
                
            # Display the first 500 characters of the result
            print(f"\n📄 The first 500 characters of the result:")
            print("-" * 60)
            print(result[:500])
            print("-" * 60)
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start Fundamental Analysis Stock Symbol Tracking Test")
    
    # test 1: Direct testing of unified tools
    success1 = test_unified_tool_direct()
    
    # test 2: Test Fundamental Analyst
    success2 = test_fundamentals_analyst()
    
    if success1 and success2:
        print("\n✅ All tests passed")
    else:
        print("\n❌ Some tests failed")
