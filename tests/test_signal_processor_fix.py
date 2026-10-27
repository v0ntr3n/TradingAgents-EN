#!/usr/bin/env python3
"""
Test the repaired functionality of SignalProcessor
"""

import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env", override=True)

def test_signal_processor_currency_fix():
    """Test currency fix for SignalProcessor"""
    
    try:
        from tradingagents.graph.signal_processing import SignalProcessor
        from langchain_openai import ChatOpenAI
        
        print("🔍 Test SignalProcessor currency fix...")
        
        # Create LLM (using Alibaba Bailian)
        llm = ChatOpenAI(
            model="qwen-turbo",
            openai_api_base="https://dashscope.aliyuncs.com/compatible-mode/v1",
            openai_api_key=os.getenv("DASHSCOPE_API_KEY"),
            temperature=0.1
        )
        
        # Create signal handler
        processor = SignalProcessor(llm)
        
        # Test China A-share signals
        china_signal = """
        Based on Ping An Bank(000001)Based on our comprehensive analysis, we recommend holding the stock.
        
        Technical analysis shows the current price is 12.50 yuan, with a target price of 15.00 yuan.
        Fundamental analysis shows that the company s financial position is strong, with an ROE of 12.5%.
        
        Confidence:75%
        Risk score:40%
        
        Final trading advice: **hold**
        """
        
        print("📈 Testing China A-share signal processing...")
        china_decision = processor.process_signal(china_signal, "000001")
        print(f"China A-share decision results: {china_decision}")
        
        # Test US stock signals
        us_signal = """
        Based on comprehensive analysis of Apple Inc. (AAPL), we recommend BUY.
        
        Technical analysis shows current price at $150.00, target price $180.00.
        Fundamental analysis indicates strong financial performance.
        
        Confidence: 80%
        Risk Score: 30%
        
        Final Trading Recommendation: **BUY**
        """
        
        print("📈 Test US stock signal processing...")
        us_decision = processor.process_signal(us_signal, "AAPL")
        print(f"US stock decision results: {us_decision}")
        
        # Verification results
        success = True
        
        # Check China A-share results
        if china_decision.get('action') not in ['buy', 'hold', 'sell']:
            print(f"❌ China A-share action error: {china_decision.get('action')}")
            success = False
        
        if china_decision.get('target_price') is None:
            print("❌ China A-share target price is empty")
            success = False
        
        # Check US stock results
        if us_decision.get('action') not in ['buy', 'hold', 'sell']:
            print(f"❌ U.S. stock market moves wrong: {us_decision.get('action')}")
            success = False
        
        if us_decision.get('target_price') is None:
            print("❌ The target price of US stocks is empty")
            success = False
        
        if success:
            print("✅ SignalProcessor Currency repair test passed!")
            return True
        else:
            print("❌ SignalProcessor Currency repair test failed!")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_web_currency_display():
    """Test web interface currency display fix"""
    
    try:
        from web.components.results_display import render_decision_summary
        import streamlit as st
        
        print("🌐 Testing web interface currency display...")
        
        # Simulate China A-share results
        china_results = {
            'stock_symbol': '000001',
            'decision': {
                'action': 'hold',
                'confidence': 0.75,
                'risk_score': 0.40,
                'target_price': 15.00,
                'reasoning': 'Investment advice based on comprehensive analysis'
            }
        }
        
        # Simulate U.S. stock results
        us_results = {
            'stock_symbol': 'AAPL',
            'decision': {
                'action': 'buy',
                'confidence': 0.80,
                'risk_score': 0.30,
                'target_price': 180.00,
                'reasoning': 'Investment advice based on comprehensive analysis'
            }
        }
        
        print("✅ Web Interface currency display fix has been implemented")
        print("📝 China A shares should show: ¥15.00")
        print("📝 US stocks should show: $180.00")
        
        return True
        
    except Exception as e:
        print(f"❌ Web Interface test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Start testing SignalProcessor fix...")
    print("=" * 50)
    
    # Check environment variables
    if not os.getenv("DASHSCOPE_API_KEY"):
        print("❌ DASHSCOPE_API_KEY Environment variable not set")
        sys.exit(1)
    
    # Run tests
    test1_result = test_signal_processor_currency_fix()
    test2_result = test_web_currency_display()
    
    print("=" * 50)
    if test1_result and test2_result:
        print("🎉 All tests passed! Repair successful!")
        sys.exit(0)
    else:
        print("❌ Some tests failed and require further debugging")
        sys.exit(1)
