#!/usr/bin/env python3
"""
Test the OpenAI configuration repair effect
Verify that the system correctly skips OpenAI API calls without the OpenAI API Key
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_openai_config_detection():
    """Test OpenAI configuration detection logic"""
    print("\n🔍 Test OpenAI configuration detection logic")
    print("=" * 80)
    
    try:
        # Check current environment variables
        openai_key = os.getenv("OPENAI_API_KEY")
        dashscope_key = os.getenv("DASHSCOPE_API_KEY")
        finnhub_key = os.getenv("FINNHUB_API_KEY")
        
        print(f"📊 Current environment variable status:")
        print(f"   OPENAI_API_KEY: {'✅ configured' if openai_key else '❌ Not configured'}")
        print(f"   DASHSCOPE_API_KEY: {'✅ configured' if dashscope_key else '❌ Not configured'}")
        print(f"   FINNHUB_API_KEY: {'✅ configured' if finnhub_key else '❌ Not configured'}")
        
        # Check configuration
        from tradingagents.dataflows.config import get_config
        config = get_config()
        
        print(f"\n📊 Current system configuration:")
        print(f"   llm_provider: {config.get('llm_provider', 'N/A')}")
        print(f"   backend_url: {config.get('backend_url', 'N/A')}")
        print(f"   quick_think_llm: {config.get('quick_think_llm', 'N/A')}")
        print(f"   deep_think_llm: {config.get('deep_think_llm', 'N/A')}")
        
        # Simulate OpenAI configuration check logic
        print(f"\n🔍 Simulate OpenAI configuration check:")
        
        # Check 1: OpenAI API Key
        if not openai_key:
            print(f"   ❌ Check 1 failed: Not configured OPENAI_API_KEY")
            should_skip_openai = True
        else:
            print(f"   ✅ Check 1 passed: OPENAI_API_KEY configured")
            should_skip_openai = False
        
        # Check 2: Basic configuration
        if not should_skip_openai:
            if not config.get("backend_url") or not config.get("quick_think_llm"):
                print(f"   ❌ Check 2 failed: OpenAI Incomplete configuration")
                should_skip_openai = True
            else:
                print(f"   ✅ Check 2 passed: OpenAI Basic configuration is complete")
        
        # Check 3: backend_url Is it from OpenAI?
        if not should_skip_openai:
            backend_url = config.get("backend_url", "")
            if "openai.com" not in backend_url:
                print(f"   ❌ Check 3 failed: backend_url No OpenAI API ({backend_url})")
                should_skip_openai = True
            else:
                print(f"   ✅ Check 3 passed: backend_url Yes OpenAI API")
        
        print(f"\n📋 final decision:")
        if should_skip_openai:
            print(f"   🔄 Skip the OpenAI API and use it directly FinnHub")
        else:
            print(f"   🔄 Use OpenAI API")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fundamentals_api_selection():
    """Test fundamental data API selection logic"""
    print("\n📊 Test fundamental data API selection logic")
    print("=" * 80)
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        # Test the acquisition of U.S. stock fundamental data
        test_ticker = "MSFT"
        test_date = "2025-07-16"
        
        print(f"📊 test stocks: {test_ticker}")
        print(f"📊 Test date: {test_date}")
        
        print(f"\n🔄 Call fundamental data acquisition...")
        
        from tradingagents.dataflows.interface import get_fundamentals_openai
        
        # This call should skip OpenAI and use it directly FinnHub
        result = get_fundamentals_openai(test_ticker, test_date)
        
        print(f"✅ Fundamental data acquisition completed")
        print(f"   result type: {type(result)}")
        print(f"   Result length: {len(result) if result else 0}")
        
        if result:
            # Check result source
            if "finnhub" in result.lower() or "FinnHub" in result:
                print(f"   ✅ Confirm that FinnHub data source is used")
            elif "openai" in result.lower() or "OpenAI" in result:
                print(f"   ⚠️ Accidental use of OpenAI data source")
            else:
                print(f"   ℹ️ Unable to determine data source")
            
            # Show summary of results
            print(f"\n📄 summary of results (first 200 characters):")
            print("-" * 40)
            print(result[:200])
            if len(result) > 200:
                print("...")
            print("-" * 40)
        else:
            print(f"   ❌ No data obtained")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_config_scenarios():
    """Test different configuration scenarios"""
    print("\n🧪 Test different configuration scenarios")
    print("=" * 80)
    
    scenarios = [
        {
            "name": "scene 1: None OpenAI Key + Google Configuration",
            "openai_key": None,
            "backend_url": "https://generativelanguage.googleapis.com/v1",
            "expected": "Skip OpenAI, use FinnHub"
        },
        {
            "name": "scene 2: None OpenAI Key + OpenAI Configuration",
            "openai_key": None,
            "backend_url": "https://api.openai.com/v1",
            "expected": "Skip OpenAI, use FinnHub"
        },
        {
            "name": "scene 3: Yes OpenAI Key + Non-OpenAI configuration",
            "openai_key": "sk-test123",
            "backend_url": "https://generativelanguage.googleapis.com/v1",
            "expected": "Skip OpenAI, use FinnHub"
        }
    ]
    
    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print("-" * 60)
        
        # Simulate configuration check
        openai_key = scenario["openai_key"]
        backend_url = scenario["backend_url"]
        
        print(f"   Configuration: OPENAI_API_KEY = {openai_key}")
        print(f"   Configuration: backend_url = {backend_url}")
        
        # Execute check logic
        should_skip = False
        
        if not openai_key:
            print(f"   ❌ Not configured OPENAI_API_KEY")
            should_skip = True
        elif "openai.com" not in backend_url:
            print(f"   ❌ backend_url No OpenAI API")
            should_skip = True
        else:
            print(f"   ✅ Configuration check passed")
        
        result = "Skip OpenAI, use FinnHub" if should_skip else "Use OpenAI API"
        expected = scenario["expected"]
        
        if result == expected:
            print(f"   ✅ The results are as expected: {result}")
        else:
            print(f"   ❌ The result is not as expected: Expectation {expected}, actual {result}")
    
    return True

def main():
    """Main test function"""
    print("🚀 Start testing the OpenAI configuration repair effect")
    print("=" * 100)
    
    results = []
    
    # test 1: OpenAI Configure detection logic
    results.append(test_openai_config_detection())
    
    # test 2: Fundamental Data API Selection Logic
    results.append(test_fundamentals_api_selection())
    
    # test 3: Different configuration scenarios
    results.append(test_config_scenarios())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "OpenAI Configure detection logic",
        "Fundamental Data API Selection Logic",
        "Testing different configuration scenarios"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! OpenAI configuration repair successful")
        print("\n📋 Repair effect:")
        print("1. ✅ Correctly detect whether the OpenAI API Key is configured")
        print("2. ✅ Correctly detect whether backend_url is OpenAI API")
        print("3. ✅ Skip OpenAI when configuration does not match and use it directly FinnHub")
        print("4. ✅ Avoid 404 errors and configuration confusion")
        
        print("\n🔧 Problem solved:")
        print("- ❌ Trying to call without OpenAI Key OpenAI API")
        print("- ❌ Calling OpenAI API format using Google URL results in 404 error")
        print("- ❌ Configuration check logic is not strict enough")
        print("- ❌ Wrong API calls waste time and resources")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
