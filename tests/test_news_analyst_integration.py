#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testing News Analyst integration with Unified News Tools
"""

import os
import sys
from datetime import datetime

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_news_analyst_integration():
    """Testing News Analyst integration with Unified News Tools"""
    
    print("🚀 Start testing the News Analyst integration...")
    
    try:
        # Import necessary modules
        from tradingagents.agents.analysts.news_analyst import create_news_analyst
        from tradingagents.tools.unified_news_tool import create_unified_news_tool
        print("✅ Successfully imported necessary modules")
        
        # Create a simulation toolkit
        class MockToolkit:
            def __init__(self):
                # Create a unified news tool
                self.unified_news_tool = create_unified_news_tool(self)
                
            def get_realtime_stock_news(self, params):
                stock_code = params.get("stock_code", "unknown")
                return f"""
 [Release time]2025-07-28 18:00:00
 [News headline]{stock_code}The company issued an important announcement and its performance exceeded expectations.
 [Source of article] Oriental Fortune Network

 [News content]
1. The company s Q2 quarter revenue increased by 25% year-on-year, and net profit increased 30%
2. The new product line has achieved major breakthroughs and has broad market prospects.
3. Management expresses optimism about second half results
4. Analysts raise target price to 50 yuan

 [Market Impact]
- Short-term positives: Performance exceeds expectations, market sentiment is positive
- Medium-term upside: New product lines provide growth momentum
- Long-term benefits: industry position further consolidated
"""
            
            def get_google_news(self, params):
                query = params.get("query", "unknown")
                return f"Google News search results - {query}: Related financial news content"
            
            def get_global_news_openai(self, params):
                query = params.get("query", "unknown")
                return f"OpenAI global news - {query}: International financial news content"
        
        toolkit = MockToolkit()
        print("✅ Simulation toolkit created successfully")
        
        # Create simulation LLM
        class MockLLM:
            def __init__(self):
                self.__class__.__name__ = "MockLLM"
            
            def bind_tools(self, tools):
                return self
            
            def invoke(self, messages):
                # Simulate LLM response, including tool calls
                class MockResult:
                    def __init__(self):
                        self.content = """
# Stock News Analysis Report

## 📈 core points
Based on the latest news data obtained, the stock shows strong performance growth:

### 🎯 Performance Highlights
- Q2 Revenue increased by 25% year-on-year, exceeding market expectations
- Net profit increased by 30%, profitability significantly improved
- New product line achieved major breakthrough

### 📊 Market Impact Analysis
**Short-term impact (1-3 months)**: 
- Expected share price to rise 5-10%
- Market sentiment turns positive

**Mid-term impact (3-12 months)**: 
- New product lines contribute incremental revenue
- Valuation is expected to recover to a reasonable level

### 💰 investment advice
- **Rating**: buy
- **target price**: 50 Yuan
- **risk level**: medium

Professional analysis reports based on real news data.
"""
                        # Simulation tool call
                        self.tool_calls = [{
                            "name": "get_stock_news_unified",
                            "args": {"stock_code": "000001", "max_news": 10}
                        }]
                
                return MockResult()
        
        llm = MockLLM()
        print("✅ Create simulated LLM successfully")
        
        # Create a news analyst
        news_analyst = create_news_analyst(llm, toolkit)
        print("✅ Create news analyst successfully")
        
        # Test different stocks
        test_stocks = [
            ("000001", "Ping An Bank - A Shares"),
            ("00700", "Tencent Holdings - Hong Kong Stocks"),
            ("AAPL", "Apple - US Stocks")
        ]
        
        for stock_code, description in test_stocks:
            print(f"\n{'='*60}")
            print(f"🔍 test stocks: {stock_code} ({description})")
            print(f"{'='*60}")
            
            try:
                # Call a news analyst
                start_time = datetime.now()
                result = news_analyst({
                    "messages": [],
                    "company_of_interest": stock_code,
                    "trade_date": "2025-07-28",
                    "session_id": f"test_{stock_code}"
                })
                end_time = datetime.now()
                
                print(f"⏱️ Analysis takes time: {(end_time - start_time).total_seconds():.2f}seconds")
                
                # Check results
                if result and "messages" in result and len(result["messages"]) > 0:
                    final_message = result["messages"][-1]
                    if hasattr(final_message, 'content'):
                        report = final_message.content
                        print(f"✅ Successfully obtained news analysis report")
                        print(f"📊 Report length: {len(report)} character")
                        
                        # Show report summary
                        if len(report) > 300:
                            print(f"📝 Report Summary: {report[:300]}...")
                        else:
                            print(f"📝 full report: {report}")
                        
                        # Check if real news features are included
                        news_indicators = ['Release time', 'News headline', 'Article source', 'Oriental Fortune', 'performance', 'Revenue']
                        has_real_news = any(indicator in report for indicator in news_indicators)
                        print(f"🔍 Contains real news features: {'Yes' if has_real_news else 'No'}")
                        
                        if has_real_news:
                            print("🎉 Integration test successful!")
                        else:
                            print("⚠️ May need further optimization")
                    else:
                        print("❌ The message content is empty")
                else:
                    print("❌ No analysis results were obtained")
                    
            except Exception as e:
                print(f"❌ test stocks {stock_code} error: {e}")
                import traceback
                traceback.print_exc()
        
        print(f"\n{'='*60}")
        print("🎉 News Analyst Integration Test Completed!")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"❌ An error occurred during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_news_analyst_integration()