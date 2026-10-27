#!/usr/bin/env python3
"""
Complete fundamental analysis process test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_full_fundamentals_flow():
    """Test the complete fundamental analysis process"""
    print("\n🔍 Complete fundamental analysis process test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print(f"\n🔧 steps 1: Initialize LLM and toolkit...")
        
        # Import necessary modules
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.llm_adapters import get_llm

        # Get LLM instance
        llm = get_llm()
        print(f"✅ LLM Initialization completed: {type(llm).__name__}")

        # Create toolkit
        toolkit = Toolkit()
        print(f"✅ Toolkit initialization completed")
        
        print(f"\n🔧 steps 2: Create a fundamental analyst...")
        
        # Create a fundamental analyst
        fundamentals_analyst = create_fundamentals_analyst(llm, toolkit)
        print(f"✅ Fundamental Analyst is created")
        
        print(f"\n🔧 steps 3: Ready to analyze status...")
        
        # Create analysis status
        state = {
            "company_of_interest": test_ticker,
            "trade_date": "2025-07-15",
            "messages": []
        }
        
        print(f"✅ Analysis status ready")
        print(f"   - Stock code: {state['company_of_interest']}")
        print(f"   - transaction date: {state['trade_date']}")
        print(f"   - Number of messages: {len(state['messages'])}")
        
        print(f"\n🔧 steps 4: Perform fundamental analysis...")
        
        # Perform fundamental analysis
        result = fundamentals_analyst(state)
        
        print(f"\n✅ Fundamental analysis execution completed")
        print(f"📊 Return result type: {type(result)}")
        
        # Check the returned results
        if isinstance(result, dict):
            if 'fundamentals_report' in result:
                report = result['fundamentals_report']
                print(f"📄 Fundamental report length: {len(report) if report else 0}")
                
                # Check the stock symbol in the report
                if report:
                    print(f"\n🔍 Stock code in final inspection report...")
                    if "002027" in report:
                        print("✅ Reports contain correct ticker symbols 002027")
                        count_002027 = report.count("002027")
                        print(f"   002027 Number of occurrences: {count_002027}")
                    else:
                        print("❌ Report does not contain correct ticker symbol 002027")
                        
                    if "002021" in report:
                        print("⚠️ Report contains incorrect stock symbol 002021")
                        count_002021 = report.count("002021")
                        print(f"   002021 Number of occurrences: {count_002021}")
                        
                        # Find the location of the error code
                        import re
                        positions = [m.start() for m in re.finditer("002021", report)]
                        print(f"   002021 Appear location: {positions}")
                        
                        # Show text around error code
                        for pos in positions[:3]:  # Only show first 3 positions
                            start = max(0, pos - 100)
                            end = min(len(report), pos + 100)
                            context = report[start:end]
                            print(f"   location {pos} surrounding text: ...{context}...")
                    else:
                        print("✅ Reports do not contain incorrect ticker symbols 002021")
                        
                    # Display the first 1000 characters of the report
                    print(f"\n📄 Report first 1000 characters:")
                    print("-" * 80)
                    print(report[:1000])
                    print("-" * 80)
            else:
                print("❌ There is no return result fundamentals_report")
                print(f"   Return result key: {list(result.keys())}")
        else:
            print(f"❌ The return result type is incorrect: {type(result)}")
            if hasattr(result, 'content'):
                print(f"   content: {result.content[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start testing the complete fundamental analysis process")
    
    # Perform complete process testing
    success = test_full_fundamentals_flow()
    
    if success:
        print("\n✅ Test completed")
    else:
        print("\n❌ test failed")
