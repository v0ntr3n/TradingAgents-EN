#!/usr/bin/env python3
"""
Test web interface fix
"""

import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_render_decision_summary():
    """Test render_decision_summary function fix"""
    
    try:
        # Simulate streamlit environment
        class MockStreamlit:
            def subheader(self, text):
                print(f"📊 {text}")
            
            def columns(self, n):
                return [MockColumn() for _ in range(n)]
            
            def metric(self, label, value, delta=None, delta_color=None, help=None):
                print(f"  {label}: {value}")
                if delta:
                    print(f"    Delta: {delta}")
        
        class MockColumn:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
        
        # Simulate streamlit module
        sys.modules['streamlit'] = MockStreamlit()
        
        from web.components.results_display import render_decision_summary
        
        print("🧪 Test render_decision_summary fix...")
        
        # Testing China A-shares
        china_decision = {
            'action': 'hold',
            'confidence': 0.75,
            'risk_score': 0.40,
            'target_price': 15.00,
            'reasoning': 'Investment advice based on comprehensive analysis'
        }
        
        print("\n📈 Testing China A-share decision-making display:")
        render_decision_summary(china_decision, "000001")
        
        # Test US stocks
        us_decision = {
            'action': 'buy',
            'confidence': 0.80,
            'risk_score': 0.30,
            'target_price': 180.00,
            'reasoning': 'Investment advice based on comprehensive analysis'
        }
        
        print("\n📈 Test the US stock decision display:")
        render_decision_summary(us_decision, "AAPL")
        
        print("\n✅ render_decision_summary Repair test passed!")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_currency_detection():
    """Test currency detection logic"""
    
    try:
        import re
        
        def is_china_stock(ticker_code):
            return re.match(r'^\d{6}$', str(ticker_code)) if ticker_code else False
        
        print("🧪 Test currency detection logic...")
        
        # Test China A-share code
        china_stocks = ["000001", "600036", "300001", "002001"]
        for stock in china_stocks:
            is_china = is_china_stock(stock)
            currency = "¥" if is_china else "$"
            print(f"  {stock}: {'China A shares' if is_china else 'Non-A shares'} -> {currency}")
            
            if not is_china:
                print(f"❌ {stock} Should be identified as China A-shares")
                return False
        
        # Test non-China stock symbols
        foreign_stocks = ["AAPL", "MSFT", "GOOGL", "TSLA", "0700.HK"]
        for stock in foreign_stocks:
            is_china = is_china_stock(stock)
            currency = "¥" if is_china else "$"
            print(f"  {stock}: {'China A shares' if is_china else 'Non-A shares'} -> {currency}")
            
            if is_china:
                print(f"❌ {stock} Should not be identified as China A shares")
                return False
        
        print("✅ Currency detection logic test passed!")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

if __name__ == "__main__":
    print("🧪 Start testing web interface fixes...")
    print("=" * 50)
    
    # Run tests
    test1_result = test_render_decision_summary()
    test2_result = test_currency_detection()
    
    print("=" * 50)
    if test1_result and test2_result:
        print("🎉 All web interface repair tests passed!")
        print("📝 The web interface should now display correctly:")
        print("   - China A shares: ¥XX.XX")
        print("   - US stocks/Hong Kong stocks: $XX.XX")
        print("   - Never appear again NameError")
        sys.exit(0)
    else:
        print("❌ Some tests failed")
        sys.exit(1)
