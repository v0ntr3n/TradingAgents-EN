#!/usr/bin/env python3
"""
Simple fundamental analysis test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_simple_fundamentals():
    """Test a simple fundamental analysis process"""
    print("\n🔍 Simple fundamental analysis test")
    print("=" * 80)
    
    # Test Focus Media 002027
    test_ticker = "002027"
    print(f"📊 Test ticker: {test_ticker} (focus media)")
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print(f"\n🔧 steps 1: Create LLM instance...")
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, skipping LLM test")
            return True
        
        # Create LLM instance
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=1000
        )
        print(f"✅ LLM Instance creation completed: {type(llm).__name__}")
        
        print(f"\n🔧 steps 2: Create toolkit...")
        
        # Create toolkit
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit()
        toolkit.update_config(config)
        print(f"✅ Toolkit created")
        
        print(f"\n🔧 steps 3: Test Unified Fundamentals Tool...")
        
        # Direct testing of unified fundamental tools
        result = toolkit.get_stock_fundamentals_unified.invoke({
            'ticker': test_ticker,
            'start_date': '2025-06-01',
            'end_date': '2025-07-15',
            'curr_date': '2025-07-15'
        })
        
        print(f"✅ Unified fundamental tool call completed")
        print(f"📊 Return result length: {len(result) if result else 0}")
        
        # Check the stock symbol in the results
        if result:
            print(f"\n🔍 Check the ticker in tool return results...")
            if "002027" in result:
                print("✅ The tool returns results that contain the correct ticker symbol 002027")
                count_002027 = result.count("002027")
                print(f"   002027 Number of occurrences: {count_002027}")
            else:
                print("❌ Tool return results do not contain correct stock symbol 002027")
                
            if "002021" in result:
                print("⚠️ Tool returns results containing wrong stock symbol 002021")
                count_002021 = result.count("002021")
                print(f"   002021 Number of occurrences: {count_002021}")
            else:
                print("✅ Tool return results do not contain incorrect stock symbols 002021")
        
        print(f"\n🔧 steps 4: Test LLM processing...")
        
        # Create a simple prompt word containing the data returned by the tool
        prompt = f"""Please base your opinion on the stock based on the following real data{test_ticker}Perform fundamental analysis:

{result}

Requirements:
1. The analysis must be detailed and professional
2. Must use Chinese
3. Stock code must be accurate
4. Don t make up any information
"""
        
        print(f"🔍 [Stock symbol tracking] Stock symbol in prompt word sent to LLM: {test_ticker}")
        
        # call LLM
        from langchain_core.messages import HumanMessage
        response = llm.invoke([HumanMessage(content=prompt)])
        
        print(f"✅ LLM Call completed")
        print(f"📊 LLM response length: {len(response.content) if response.content else 0}")
        
        # Check the stock symbol in the LLM response
        if response.content:
            print(f"\n🔍 Check the stock symbol in the LLM response...")
            if "002027" in response.content:
                print("✅ LLM The response contains the correct ticker symbol 002027")
                count_002027 = response.content.count("002027")
                print(f"   002027 Number of occurrences: {count_002027}")
            else:
                print("❌ LLM Response does not contain correct ticker symbol 002027")
                
            if "002021" in response.content:
                print("⚠️ LLM Response contains wrong stock symbol 002021")
                count_002021 = response.content.count("002021")
                print(f"   002021 Number of occurrences: {count_002021}")
                
                # Find the location of the error code
                import re
                positions = [m.start() for m in re.finditer("002021", response.content)]
                print(f"   002021 Appear location: {positions}")
                
                # Show text around error code
                for pos in positions[:3]:  # Only show first 3 positions
                    start = max(0, pos - 100)
                    end = min(len(response.content), pos + 100)
                    context = response.content[start:end]
                    print(f"   location {pos} surrounding text: ...{context}...")
            else:
                print("✅ LLM The response does not contain the wrong stock symbol 002021")
                
            # Display the first 1000 characters of the LLM response
            print(f"\n📄 LLM First 1000 characters of response:")
            print("-" * 80)
            print(response.content[:1000])
            print("-" * 80)
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Start a simple fundamental analysis test")
    
    # Execute tests
    success = test_simple_fundamentals()
    
    if success:
        print("\n✅ Test completed")
    else:
        print("\n❌ test failed")
