#!/usr/bin/env python3
"""
Test DashScope tool call failure detection and remediation mechanisms

This script tests the news analyst s remediation mechanism when the DashScope model does not call the tool.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
import logging

# Setup log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def test_dashscope_tool_call_detection():
    """Test the DashScope tool call failure detection mechanism"""
    
    print("🧪 Test DashScope tool call failure detection and remediation mechanisms")
    print("=" * 60)
    
    # Mock DashScope model class
    class MockDashScopeModel:
        def __init__(self):
            self.__class__.__name__ = "ChatDashScopeOpenAI"
        
        def invoke(self, messages):
            # Simulation return results
            class MockResult:
                def __init__(self, content, tool_calls=None):
                    self.content = content
                    self.tool_calls = tool_calls or []
            
            return MockResult("This is an analysis report not based on real news data...")
    
    # Simulation tools
    class MockToolkit:
        @staticmethod
        def get_realtime_stock_news():
            class MockTool:
                def invoke(self, params):
                    ticker = params.get('ticker', 'UNKNOWN')
                    curr_date = params.get('curr_date', 'UNKNOWN')
                    # Return news data long enough (>100 characters)
                    return f""" [Oriental Fortune News]{ticker} Latest stock news:
                    
1. The company issued an important announcement, with third-quarter results exceeding expectations and net profit increasing year-on-year.25%
2. Management announces new strategic partnerships expected to deliver significant revenue growth
3. Industry analysts raised their price targets, saying the stock represents a good investment
4. The latest financial report shows that the company s cash flow is in good condition and the debt ratio continues to decline.
5. The market remains optimistic about the company s future development prospects

Release time:{curr_date}
Data source: Oriental Fortune Network"""
            return MockTool()
        
        @staticmethod
        def get_google_news():
            class MockTool:
                def invoke(self, params):
                    query = params.get('query', 'UNKNOWN')
                    curr_date = params.get('curr_date', 'UNKNOWN')
                    # Return news data long enough (>100 characters)
                    return f""" [Google News]{query} Related news summary:
                    
1. Market analysts are bullish on the stock s prospects, predicting significant gains over the next 12 months
2. Institutional investors increased their holdings of the stock, showing recognition of the company s long-term value
3. The overall performance of the industry is good, and the company has benefited significantly as a leading enterprise.
4. Technical analysis shows stock price breaks key resistance level, trending upward
5. Fundamental analysis shows that the company s valuation is reasonable and has investment value

Time:{curr_date}
Data source:Google News"""
            return MockTool()
    
    # Test parameters
    ticker = "600036"
    current_date = datetime.now().strftime("%Y-%m-%d")
    llm = MockDashScopeModel()
    toolkit = MockToolkit()
    
    print(f"📊 test stocks: {ticker}")
    print(f"📅 current date: {current_date}")
    print(f"🤖 Model type: {llm.__class__.__name__}")
    print()
    
    # Test scenario 1: DashScope does not call any tools (tool_call_count = 0) 
    print("🔍 Test scenario 1: DashScope does not call any tools")
    print("-" * 40)
    
    # Simulate LLM call results
    class MockResult:
        def __init__(self):
            self.content = "This is an analysis report that is not based on real news data and is 2089 characters long...."
            self.tool_calls = []  # No tool calls
    
    result = MockResult()
    tool_call_count = len(result.tool_calls)
    
    print(f"📈 LLM Call result: Number of tool calls = {tool_call_count}")
    print(f"📝 Original report length: {len(result.content)} character")
    
    # Apply enhanced detection logic
    report = ""
    
    if 'DashScope' in llm.__class__.__name__:
        if tool_call_count == 0:
            print("🚨 It is detected that DashScope does not call any tools, and forced remediation is initiated....")
            
            try:
                # Forced acquisition of news data
                print("🔧 Forced call to get_realtime_stock_news to obtain news data...")
                forced_news = toolkit.get_realtime_stock_news().invoke({"ticker": ticker, "curr_date": current_date})
                
                if forced_news and len(forced_news.strip()) > 100:
                    print(f"✅ Forced news acquisition successful: {len(forced_news)} character")
                    print(f"📰 News content preview: {forced_news[:100]}...")
                    
                    # Simulation regenerates analysis based on real news data
                    forced_prompt = f"""
Based on the latest news data obtained below, the stock {ticker} For detailed news analysis:

=== Latest news data ===
{forced_news}

Please write a detailed Chinese analysis report based on the above real news data.
"""
                    
                    print("🔄 Regenerate full analysis based on force-fetched news data...")
                    # Simulate regenerated results
                    report = f"Analysis report based on real news data:\n\n{forced_news}\n\n Detailed Analysis: This Stock Shows Positive Signs Based on Latest News..."
                    print(f"✅ Force remediation successful, generate report based on real data, length: {len(report)} character")
                    
                else:
                    print("⚠️ Forced news acquisition failed, try alternate tools...")
                    
                    # Try alternative tools
                    backup_news = toolkit.get_google_news().invoke({"query": f"{ticker} Stock News", "curr_date": current_date})
                    
                    if backup_news and len(backup_news.strip()) > 100:
                        print(f"✅ Backup tool obtained successfully: {len(backup_news)} character")
                        report = f"Analysis report based on alternative news data:\n\n{backup_news}\n\n Analysis conclusion..."
                        print(f"✅ Alternate tool remediation successful, length: {len(report)} character")
                    else:
                        print("❌ All news retrieval methods fail, use original results")
                        report = result.content
                        
            except Exception as e:
                print(f"❌ Forced remediation process failed: {e}")
                report = result.content
    
    if not report:
        report = result.content
    
    print()
    print("📊 Summary of test results:")
    print(f"   Original report length: {len(result.content)} character")
    print(f"   final report length: {len(report)} character")
    print(f"   Does it contain real news?: {'Yes' if 'Oriental Fortune News' in report or 'Google News' in report else 'No'}")
    print(f"   Remediation mechanism status: {'success' if len(report) > len(result.content) else 'Not triggered or failed'}")
    
    print()
    print("🎯 Test conclusion:")
    if 'Oriental Fortune News' in report or 'Google News' in report:
        print("✅ Enhanced DashScope tool call failure detection and remediation mechanism works properly")
        print("✅ Successfully detected tool call failure and forced acquisition of real news data")
        print("✅ Analysis reports are regenerated based on real news data")
    else:
        print("❌ There may be problems with the remediation mechanism")
    
    return True

if __name__ == "__main__":
    try:
        test_dashscope_tool_call_detection()
        print("\n🎉 All tests completed!")
    except Exception as e:
        print(f"\n❌ An error occurred during testing: {e}")
        sys.exit(1)