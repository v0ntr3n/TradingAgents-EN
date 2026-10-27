#!/usr/bin/env python3
"""
002027 Stock code special test
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_002027_specifically():
    """Specially test the 002027 stock code"""
    print("🔍 002027 special test")
    print("=" * 60)
    
    test_ticker = "002027"
    
    try:
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        # test 1: data acquisition
        print("\n📊 test 1: data acquisition")
        from tradingagents.dataflows.interface import get_china_stock_data_tushare
        data = get_china_stock_data_tushare(test_ticker, "2025-07-01", "2025-07-15")
        
        if "002021" in data:
            print("❌ Error code found during data acquisition phase 002021")
            return False
        else:
            print("✅ The data acquisition phase is correct")
        
        # test 2: fundamental analysis
        print("\n💰 test 2: fundamental analysis")
        from tradingagents.dataflows.optimized_china_data import OptimizedChinaDataProvider
        analyzer = OptimizedChinaDataProvider()
        report = analyzer._generate_fundamentals_report(test_ticker, data)
        
        if "002021" in report:
            print("❌ Error code found during fundamental analysis phase 002021")
            return False
        else:
            print("✅ Fundamental analysis stage is correct")
        
        # test 3: LLM Process
        print("\n🤖 test 3: LLM Process")
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if api_key:
            from tradingagents.llm_adapters import ChatDashScopeOpenAI
            from langchain_core.messages import HumanMessage
            
            llm = ChatDashScopeOpenAI(model="qwen-turbo", temperature=0.1, max_tokens=500)
            
            prompt = f"Please analyze the stock{test_ticker}Based on the fundamentals, the stock name is Focus Media. Requirements: 1. The correct stock code must be used{test_ticker} 2.Do not use any other stock symbol"
            
            response = llm.invoke([HumanMessage(content=prompt)])
            
            if "002021" in response.content:
                print("❌ LLM Error code found during processing 002021")
                print(f"Error content: {response.content[:200]}...")
                return False
            else:
                print("✅ LLM processing stage correct")
        else:
            print("⚠️ Skip LLM testing (no API key configured)")
        
        print("\n🎉 All tests passed! 002027 stock code is processed correctly")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    test_002027_specifically()
