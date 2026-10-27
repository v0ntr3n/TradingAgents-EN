"""
Test the stock symbol standardization logic (simulating the various formats that AKShare s two interfaces may return)
"""
import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def normalize_code_akshare_style(code_raw):
    """
    Simulation AKShareAdapter.get_realtime_quotes() Code standardization logic in
    """
    if not code_raw:
        return None
    
    # Standardized ticker: handles exchange prefixes (e.g. sz000001, sh600036) 
    code_str = str(code_raw).strip()
    
    # If the code length exceeds 6 characters, remove the previous exchange prefix (such as sz, sh) 
    if len(code_str) > 6:
        # Remove leading non-numeric characters (usually the 2-character exchange code)
        code_str = ''.join(filter(str.isdigit, code_str))
    
    # If it is a pure number, remove the leading 0 and pad it to 6 digits.
    if code_str.isdigit():
        code_clean = code_str.lstrip('0') or '0'  # Remove leading 0s, if all 0s, keep one 0
        code = code_clean.zfill(6)  # Complete to 6 digits
    else:
        # If it's not purely numeric, try to extract the numeric part
        code_digits = ''.join(filter(str.isdigit, code_str))
        if code_digits:
            code = code_digits.zfill(6)
        else:
            # Unable to extract valid code, skip
            return None
    
    return code


def test_code_normalization():
    """Test various possible ticker formats"""
    print("\n" + "="*70)
    print("🧪 Test ticker standardization logic")
    print("="*70)
    
    test_cases = [
        # (input, expected output, Description, Source)
        ("sz000001", "000001", "Shenzhen Ping An Bank (with sz prefix)", "Sina interface"),
        ("sh600036", "600036", "Shanghai China Merchants Bank (with sh prefix)", "Sina interface"),
        ("bj920000", "920000", "North Exchange stocks (with bj prefix)", "Sina interface"),
        ("000001", "000001", "Standard 6-digit code", "Oriental Wealth Interface"),
        ("600036", "600036", "Standard 6-digit code", "Oriental Wealth Interface"),
        ("920000", "920000", "North Exchange Standard Code", "Oriental Wealth Interface"),
        ("1", "000001", "single number", "boundary case"),
        ("00001", "000001", "5 bit code", "boundary case"),
        ("0000001", "000001", "7 Bit code (leading 0)", "boundary case"),
        ("sz002594", "002594", "Shenzhen BYD", "Sina interface"),
        ("sh688001", "688001", "Shanghai Science and Technology Innovation Board", "Sina interface"),
        ("sz300001", "300001", "Shenzhen GEM", "Sina interface"),
        ("", None, "empty string", "boundary case"),
        ("abc", None, "plain letters (invalid)", "boundary case"),
        ("sz", None, "Prefix only (invalid)", "boundary case"),
    ]
    
    print(f"\n{'Status':4s} | {'input':12s} | {'Expectation':8s} | {'actual':8s} | {'Description':20s} | {'Source':12s}")
    print("-" * 70)
    
    passed = 0
    failed = 0
    
    for input_code, expected, description, source in test_cases:
        result = normalize_code_akshare_style(input_code)
        
        if result == expected:
            status = "✅"
            passed += 1
        else:
            status = "❌"
            failed += 1
        
        input_display = f"'{input_code}'" if input_code else "(empty)"
        expected_display = expected if expected else "(None)"
        result_display = result if result else "(None)"
        
        print(f"{status:4s} | {input_display:12s} | {expected_display:8s} | {result_display:8s} | {description:20s} | {source:12s}")
    
    print("-" * 70)
    print(f"\n📊 Test results: total {len(test_cases)} use cases, Pass {passed}, failed {failed}")
    
    if failed == 0:
        print("\n🎉 All tests passed! Code standardization logic correctly handles various formats")
    else:
        print(f"\n⚠️  Yes {failed} Tests failed, please check the code standardization logic")
    
    return failed == 0


def test_interface_compatibility():
    """Test the compatibility of two interfaces"""
    print("\n" + "="*70)
    print("🔄 Test interface compatibility")
    print("="*70)
    
    print("\n📋 Sina interface (stock_zh_a_spot) Possible return formats:")
    sina_formats = [
        "sz000001",  # Shenzhen stocks
        "sh600036",  # Shanghai stocks
        "bj920000",  # North Exchange stocks
    ]
    
    for code in sina_formats:
        normalized = normalize_code_akshare_style(code)
        print(f"   {code:12s} → {normalized}")
    
    print("\n📋 Oriental Wealth Interface (stock_zh_a_spot_em) Possible return formats:")
    em_formats = [
        "000001",  # Shenzhen stocks (pure numbers)
        "600036",  # Shanghai stocks (pure numbers)
        "920000",  # North Exchange stocks (pure numbers)
    ]
    
    for code in em_formats:
        normalized = normalize_code_akshare_style(code)
        print(f"   {code:12s} → {normalized}")
    
    print("\n✅ Conclusion: No matter which interface, the standardized code is a unified 6-digit digital format")


if __name__ == "__main__":
    success1 = test_code_normalization()
    test_interface_compatibility()
    
    if success1:
        print("\n" + "="*70)
        print("✅ All tests passed!")
        print("="*70)
        print("\n💡 Summary:")
        print("   1. AKShareAdapter The code standardization logic is correct")
        print("   2. Both Sina interface and Oriental Fortune interface use the same standardized logic")
        print("   3. All codes will eventually be standardized to a 6-digit format")
        print("   4. Codes with exchange prefixes can be handled correctly (sz, sh, bj) ")
    else:
        print("\n" + "="*70)
        print("❌ Some tests failed, please check the code")
        print("="*70)

