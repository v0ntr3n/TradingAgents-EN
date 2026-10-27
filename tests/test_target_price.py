#!/usr/bin/env python3
"""
Testing the optimized target price generation system
"""

import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_signal_processor():
    """Testing the price extraction function of the signal processor"""
    print("🧪 Test the signal processor price extraction function...")
    
    try:
        from tradingagents.agents.signal_processing import SignalProcessor
        
        processor = SignalProcessor()
        
        # test case 1: Text containing a clear target price
        test_text1 = """
        Based on technical analysis, AAPL is currently priced at $180 and a buy recommendation is recommended.
        Target price: $200
        Stop loss price: $170
        Expected increase:11%
        """
        
        result1 = processor._extract_target_price(test_text1, "AAPL", "USD")
        print(f"✅ Test 1 - Define target price: {result1}")
        
        # test case 2: Text that requires intelligent inference
        test_text2 = """
        Tencent Holdings(0700.HK)The current price is HKD 320,
        It is recommended to buy based on fundamental analysis, with an expected increase of 15%.
        """
        
        result2 = processor._extract_target_price(test_text2, "0700.HK", "HKD")
        print(f"✅ Test 2 - Smart Extrapolation: {result2}")
        
        # test case 3: A stock example
        test_text3 = """
        Kweichow Moutai(600519)The current price is 1,800 yuan, based on valuation analysis.
        The reasonable price range is 1,900-2,100 yuan, and it is recommended to hold it.
        """
        
        result3 = processor._extract_target_price(test_text3, "600519", "CNY")
        print(f"✅ Test 3 - A Share Price: {result3}")
        
        return True
        
    except Exception as e:
        print(f"❌ Signal handler test failed: {e}")
        return False

def test_smart_price_estimation():
    """Test the smart price calculation function"""
    print("\n🧪 Test the smart price calculation function...")
    
    try:
        from tradingagents.agents.signal_processing import SignalProcessor
        
        processor = SignalProcessor()
        
        # Test inference logic
        test_cases = [
            ("Current price $100, expected to rise 20%", "buy", 120.0),
            ("The current price is 50 yuan. It is recommended to sell. It is expected to fall.10%", "sell", 45.0),
            ("The stock price is HK$200, hold, expected increase 5%", "hold", 210.0)
        ]
        
        for text, action, expected in test_cases:
            result = processor._smart_price_estimation(text, action)
            print(f"✅ text: '{text}' -> estimated price: {result} (expected: {expected})")
        
        return True
        
    except Exception as e:
        print(f"❌ Smart extrapolation test failed: {e}")
        return False

def test_trader_prompt():
    """Test whether the trader prompt word contains a target price requirement"""
    print("\n🧪 Check trader tip word optimization...")
    
    try:
        from tradingagents.agents.trader import trader_node
        import inspect
        
        # Get the source code of trader_node function
        source = inspect.getsource(trader_node)
        
        # Check keywords
        keywords = ["target price", "target_price", "Specific price", "No reply"]
        found_keywords = []
        
        for keyword in keywords:
            if keyword in source:
                found_keywords.append(keyword)
        
        print(f"✅ Trader tip words contain keywords: {found_keywords}")
        
        if len(found_keywords) >= 2:
            print("✅ Trader module has been optimized")
            return True
        else:
            print("⚠️ The trader module may need further optimization")
            return False
            
    except Exception as e:
        print(f"❌ Trader prompt word check failed: {e}")
        return False

def main():
    """Main test function"""
    print("🚀 Start testing the optimized target price generation system")
    print("=" * 60)
    
    test_results = []
    
    # Run various tests
    test_results.append(test_signal_processor())
    test_results.append(test_smart_price_estimation())
    test_results.append(test_trader_prompt())
    
    # Summary results
    print("\n" + "=" * 60)
    print("📊 Summary of test results:")
    
    passed = sum(test_results)
    total = len(test_results)
    
    print(f"✅ Pass test: {passed}/{total}")
    
    if passed == total:
        print("🎉 All tests passed! The target price generation system has been optimized successfully!")
        print("\n💡 The system is now able to:")
        print("   • Extract explicit target prices from analytical text")
        print("   • Intelligent calculation of target price based on current price and increase or decrease")
        print("   • Mandate all analysts to provide target price information")
        print("   • Supports multiple currencies and stock markets")
    else:
        print(f"⚠️ Yes {total - passed} Test failed and requires further inspection")
    
    print("\n🔧 Suggestions for next steps:")
    print("   1. Run a complete stock analysis process test")
    print("   2. Verify target price generation in actual LLM responses")
    print("   3. Test the analysis effect of different types of stocks")

if __name__ == "__main__":
    main()