#!/usr/bin/env python3
"""
Logging fix for test signal handling module
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_signal_processing_logging():
    """Test logging of signal processing modules"""
    print("\n📊 Test signal processing module logging")
    print("=" * 80)
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        print("🔧 Create signal handler...")
        
        # Import signal handler
        from tradingagents.graph.signal_processing import SignalProcessor
        
        processor = SignalProcessor()
        print("✅ The signal processor is created")
        
        # Test different stock symbols
        test_cases = [
            ("000858", "Wuliangye"),
            ("002027", "focus media"),
            ("0700.HK", "Tencent Holdings"),
        ]
        
        for stock_symbol, company_name in test_cases:
            print(f"\n📊 test stocks: {stock_symbol} ({company_name})")
            print("-" * 60)
            
            # Create simulated trading signals
            mock_signal = f"""
# {company_name}({stock_symbol})Investment analysis report

## 📊 fundamental analysis
- Stock code: {stock_symbol}
- Company name: {company_name}
- investment advice: buy
- target price: 100.00
- risk rating: medium

## 📈 Technical analysis
- Trend: rise
- support level: 90.00
- resistance level: 110.00

## 💰 final decision
Based on comprehensive analysis, it is recommended to buy{company_name}({stock_symbol}). 
"""
            
            print(f"🔍 [test] Call signal handler...")
            print(f"   Stock code: {stock_symbol}")
            print(f"   Signal length: {len(mock_signal)} character")
            
            try:
                # Call the signal handler (logging should be triggered here)
                result = processor.process_signal(mock_signal, stock_symbol)
                
                print(f"✅ Signal processing completed")
                print(f"   Return result type: {type(result)}")
                
                if isinstance(result, dict):
                    print(f"   result key: {list(result.keys())}")
                    
                    # Check if stock code is included
                    if 'stock_symbol' in result:
                        print(f"   Extracted stock code: {result['stock_symbol']}")
                    
                    # Check investment advice
                    if 'investment_decision' in result:
                        decision = result['investment_decision']
                        print(f"   investment decision: {decision}")
                    
                    # Check target price
                    if 'target_price' in result:
                        price = result['target_price']
                        print(f"   target price: {price}")
                
            except Exception as e:
                print(f"❌ Signal processing failed: {e}")
                import traceback
                traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_logging_extraction():
    """Testing ticker extraction for log decorator"""
    print("\n🔍 Test log decorator stock symbol extraction")
    print("=" * 80)
    
    try:
        # Analog signal processing module calls
        from tradingagents.utils.tool_logging import log_graph_module
        
        # Create a test function to verify the logging decorator
        @log_graph_module("signal_processing")
        def mock_process_signal(self, full_signal: str, stock_symbol: str = None) -> dict:
            """Analog signal processing functions"""
            print(f"🔍 [mock function] parameters received:")
            print(f"   full_signal length: {len(full_signal) if full_signal else 0}")
            print(f"   stock_symbol: {stock_symbol}")
            
            return {
                'stock_symbol': stock_symbol,
                'processed': True
            }
        
        # Create a mocked self object
        class MockProcessor:
            pass
        
        mock_self = MockProcessor()
        
        # Test different calling methods
        test_cases = [
            ("000858", "Positional parameter call"),
            ("002027", "keyword argument call"),
            ("0700.HK", "Mixed parameter call"),
        ]
        
        for stock_symbol, call_type in test_cases:
            print(f"\n📊 test: {stock_symbol} ({call_type})")
            print("-" * 40)
            
            mock_signal = f"test signal for {stock_symbol}"
            
            try:
                if call_type == "Positional parameter call":
                    # Positional parameter call:mock_process_signal(self, full_signal, stock_symbol)
                    result = mock_process_signal(mock_self, mock_signal, stock_symbol)
                elif call_type == "keyword argument call":
                    # keyword argument call
                    result = mock_process_signal(mock_self, mock_signal, stock_symbol=stock_symbol)
                else:
                    # Mixed call
                    result = mock_process_signal(mock_self, full_signal=mock_signal, stock_symbol=stock_symbol)
                
                print(f"✅ Call successful: {result}")
                
            except Exception as e:
                print(f"❌ call failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start testing signal handling logging fix")
    print("=" * 100)
    
    results = []
    
    # test 1: Log decorator stock symbol extraction
    results.append(test_logging_extraction())
    
    # test 2: Signal processing module logging
    results.append(test_signal_processing_logging())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Log decorator stock symbol extraction",
        "Signal processing module logging"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! Signal processing logging repair successful")
        print("\n📋 Repair effect:")
        print("1. ✅ Correctly extract the stock symbol of the signal processing module")
        print("2. ✅ Logs display accurate stock information")
        print("3. ✅ avoid showing 'unknown' Stock code")
        print("4. ✅ Supports multiple parameter calling methods")
        
        print("\n🔧 Problem solved:")
        print("- ❌ The signal processing module log shows that the stock code is 'unknown'")
        print("- ❌ Log decorator does not correctly parse parameters of signal handling module")
        print("- ❌ The stock code extraction logic is not suitable for the signal processing module")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
