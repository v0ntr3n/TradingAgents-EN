#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the integration effect of unified news tools
"""

import os
import sys
from datetime import datetime

# Add project root directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.analysts.news_analyst import create_news_analyst
from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek

def test_unified_news_tool():
    """Test the integration of unified news tools"""
    
    print("🚀 Start testing the unified news tools integration...")
    
    # Test stock list - including A shares, Hong Kong stocks, and US stocks
    test_stocks = [
        ("000001", "Ping An Bank - A Shares"),
        ("00700", "Tencent Holdings - Hong Kong Stocks"), 
        ("AAPL", "Apple - US Stocks")
    ]
    
    try:
        # Initialization kit
        print("📦 Initialization kit...")
        from tradingagents.default_config import DEFAULT_CONFIG
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config=config)
        
        # Create LLM instance (using DeepSeek)
        print("🤖 Create LLM instance...")
        llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1
        )
        
        # Create a news analyst
        print("📰 Create a news analyst...")
        news_analyst = create_news_analyst(llm, toolkit)
        
        # Test every stock
        for stock_code, description in test_stocks:
            print(f"\n{'='*60}")
            print(f"🔍 test stocks: {stock_code} ({description})")
            print(f"{'='*60}")
            
            try:
                # Call a news analyst
                result = news_analyst({
                    "messages": [],
                    "company_of_interest": stock_code,
                    "trade_date": "2025-07-28",
                    "session_id": f"test_{stock_code}"
                })
                
                # Check results
                if result and "messages" in result and len(result["messages"]) > 0:
                    final_message = result["messages"][-1]
                    if hasattr(final_message, 'content'):
                        report = final_message.content
                        print(f"✅ Successfully obtained news analysis report")
                        print(f"📊 Report length: {len(report)} character")
                        
                        # Show report summary
                        if len(report) > 200:
                            print(f"📝 Report Summary: {report[:200]}...")
                        else:
                            print(f"📝 full report: {report}")
                            
                        # Check if real news features are included
                        news_indicators = ['Release time', 'News headline', 'Article source', 'Oriental Fortune', 'Financial Associated Press', 'Securities Times']
                        has_real_news = any(indicator in report for indicator in news_indicators)
                        print(f"🔍 Contains real news features: {'Yes' if has_real_news else 'No'}")
                    else:
                        print("❌ The message content is empty")
                else:
                    print("❌ News analysis report not obtained")
                    
            except Exception as e:
                print(f"❌ test stocks {stock_code} error: {e}")
                import traceback
                traceback.print_exc()
                
        print(f"\n{'='*60}")
        print("🎉 Unified news tool testing completed!")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"❌ An error occurred during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_unified_news_tool()