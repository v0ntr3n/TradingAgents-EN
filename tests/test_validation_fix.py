"""
Test Hong Kong stock verification repair
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_hk_validation():
    """Test Hong Kong stock verification"""
    print("🧪 Test Hong Kong stock verification repair...")
    
    try:
        from web.utils.analysis_runner import validate_analysis_params
        
        # test case
        test_cases = [
            # (Stock code, market type, should pass verification)
            ("0700.HK", "Hong Kong stocks", True),
            ("9988.HK", "Hong Kong stocks", True),
            ("3690.HK", "Hong Kong stocks", True),
            ("0700", "Hong Kong stocks", True),
            ("9988", "Hong Kong stocks", True),
            ("3690", "Hong Kong stocks", True),
            ("AAPL", "Hong Kong stocks", False),  # US stock code
            ("000001", "Hong Kong stocks", False),  # A stock code
            ("00", "Hong Kong stocks", False),  # too short
            ("12345", "Hong Kong stocks", False),  # too long
            ("ABC.HK", "Hong Kong stocks", False),  # Not a number
        ]
        
        passed = 0
        total = len(test_cases)
        
        for symbol, market_type, should_pass in test_cases:
            is_valid, errors = validate_analysis_params(
                stock_symbol=symbol,
                analysis_date="2025-07-14",
                analysts=["market"],
                research_depth=3,
                market_type=market_type
            )

            validation_passed = is_valid
            
            if validation_passed == should_pass:
                print(f"  ✅ {symbol} ({market_type}): {'Pass' if validation_passed else 'failed'}")
                passed += 1
            else:
                print(f"  ❌ {symbol} ({market_type}): Expectation{'Pass' if should_pass else 'failed'}, actual{'Pass' if validation_passed else 'failed'}")
                if errors:
                    print(f"      Error: {errors}")
        
        print(f"\n Verify test results: {passed}/{total} Pass")
        
        if passed == total:
            print("🎉 All validation tests passed!")
            return True
        else:
            print("⚠️ Some validation tests failed")
            return False
        
    except Exception as e:
        print(f"❌ Validation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_specific_case():
    """Test the specific 0700.HK case"""
    print("\n🧪 Test the specific 0700.HK case...")
    
    try:
        from web.utils.analysis_runner import validate_analysis_params
        
        # test 0700.HK
        is_valid, errors = validate_analysis_params(
            stock_symbol="0700.HK",
            analysis_date="2025-07-14",
            analysts=["market", "fundamentals"],
            research_depth=3,
            market_type="Hong Kong stocks"
        )

        print(f"  Stock code: 0700.HK")
        print(f"  market type: Hong Kong stocks")
        print(f"  Verification results: {'Pass' if is_valid else 'failed'}")

        if not is_valid:
            print(f"  error message: {errors}")
            return False
        else:
            print("  ✅ 0700.HK Verification passed!")
            return True
        
    except Exception as e:
        print(f"❌ Specific case test failed: {e}")
        return False

def test_regex_patterns():
    """Test regular expression pattern"""
    print("\n🧪 Test regular expression pattern...")
    
    try:
        import re
        
        # Test Hong Kong stock regular mode (supports 4-5 digits)
        hk_pattern = r'^\d{4,5}\.HK$'
        digit_pattern = r'^\d{4}$'
        
        test_symbols = [
            "0700.HK",
            "9988.HK", 
            "3690.HK",
            "0700",
            "9988",
            "3690",
            "AAPL",
            "000001",
            "ABC.HK"
        ]
        
        for symbol in test_symbols:
            symbol_upper = symbol.upper()
            hk_match = re.match(hk_pattern, symbol_upper)
            digit_match = re.match(digit_pattern, symbol)
            
            matches = bool(hk_match or digit_match)
            
            print(f"  {symbol}: HK Format={bool(hk_match)}, Number format={bool(digit_match)}, overall match={matches}")
        
        return True
        
    except Exception as e:
        print(f"❌ Regular expression test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 Hong Kong stock verification and repair test")
    print("=" * 40)
    
    tests = [
        test_regex_patterns,
        test_specific_case,
        test_hk_validation
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 40)
    print(f"🔧 Repair test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 Hong Kong stock verification and repair successful!")
        print("\n Now you can use 0700.HK for analysis normally.")
    else:
        print("⚠️ Fix may be incomplete, please check for failing tests")

if __name__ == "__main__":
    main()
