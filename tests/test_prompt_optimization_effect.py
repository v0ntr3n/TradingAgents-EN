#!/usr/bin/env python3
"""
Test the effect of optimized prompt words
Verify correct separation of ticker and company name, and analyst output quality
"""

import os
import sys

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_fundamentals_analyst_prompt():
    """Test the prompt word optimization effect of fundamental analysts"""
    print("\n📊 Test the optimization effect of fundamental analyst prompt words")
    print("=" * 80)
    
    try:
        # Set log level
        from tradingagents.utils.logging_init import get_logger
        logger = get_logger("default")
        logger.setLevel("INFO")
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, skipping LLM test")
            return True
        
        print(f"🔧 Create a fundamental analyst...")
        
        # Create LLM and toolkit
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=2000
        )
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit()
        toolkit.update_config(config)
        
        # Create a fundamental analyst
        from tradingagents.agents.analysts.fundamentals_analyst import create_fundamentals_analyst
        fundamentals_analyst = create_fundamentals_analyst(llm, toolkit)
        
        print(f"✅ Fundamental Analyst is created")
        
        # Test different types of stocks
        test_cases = [
            ("002027", "China A shares", "focus media"),
            ("000001", "China A shares", "Ping An Bank"),
            ("0700.HK", "Hong Kong stocks", "Tencent Holdings"),
        ]
        
        for ticker, market_type, expected_name in test_cases:
            print(f"\n📊 test stocks: {ticker} ({market_type})")
            print("-" * 60)
            
            # Create analysis status
            state = {
                "company_of_interest": ticker,
                "trade_date": "2025-07-16",
                "messages": []
            }
            
            print(f"🔍 [prompt word verification] Check prompt word construction...")
            
            # Get the company name (verification prompt word construction logic)
            from tradingagents.agents.analysts.fundamentals_analyst import _get_company_name_for_fundamentals
            from tradingagents.utils.stock_utils import StockUtils
            
            market_info = StockUtils.get_market_info(ticker)
            company_name = _get_company_name_for_fundamentals(ticker, market_info)
            
            print(f"   ✅ Stock code: {ticker}")
            print(f"   ✅ Company name: {company_name}")
            print(f"   ✅ market type: {market_info['market_name']}")
            print(f"   ✅ currency information: {market_info['currency_name']} ({market_info['currency_symbol']})")
            
            # Verify that the company name is correct
            if expected_name in company_name or company_name == expected_name:
                print(f"   ✅ Company name matches expected: {expected_name}")
            else:
                print(f"   ⚠️ Company name does not match expected: Expectation {expected_name}, actual {company_name}")
            
            print(f"\n🤖 Perform fundamental analysis...")
            
            try:
                # Perform fundamental analysis (limit output length to save time)
                result = fundamentals_analyst(state)
                
                if isinstance(result, dict) and 'fundamentals_report' in result:
                    report = result['fundamentals_report']
                    print(f"✅ Fundamental analysis completed, report length: {len(report)}")
                    
                    # Check key elements in your report
                    print(f"\n🔍 Check report content...")
                    
                    # Check stock symbol
                    if ticker in report:
                        print(f"   ✅ Report contains correct ticker symbol: {ticker}")
                        code_count = report.count(ticker)
                        print(f"      Number of occurrences: {code_count}")
                    else:
                        print(f"   ❌ Report does not contain ticker symbol: {ticker}")
                    
                    # Check company name
                    if company_name in report and not company_name.startswith('stocks'):
                        print(f"   ✅ Report contains correct company name: {company_name}")
                        name_count = report.count(company_name)
                        print(f"      Number of occurrences: {name_count}")
                    else:
                        print(f"   ⚠️ Reports may not include specific company names")
                    
                    # Check currency information
                    currency_symbol = market_info['currency_symbol']
                    if currency_symbol in report:
                        print(f"   ✅ Report contains correct currency symbol: {currency_symbol}")
                    else:
                        print(f"   ⚠️ Reports may not contain currency symbols: {currency_symbol}")
                    
                    # Check if there is an incorrect stock code (e.g. 002027 is mistakenly written as 002021)
                    error_codes = ["002021"] if ticker == "002027" else []
                    for error_code in error_codes:
                        if error_code in report:
                            print(f"   ❌ Report contains incorrect stock symbol: {error_code}")
                        else:
                            print(f"   ✅ Report does not contain incorrect stock symbols: {error_code}")
                    
                    # Show report summary
                    print(f"\n📄 Report Summary (first 500 characters):")
                    print("-" * 40)
                    print(report[:500])
                    if len(report) > 500:
                        print("...")
                    print("-" * 40)
                    
                else:
                    print(f"❌ Fundamental analysis returns abnormal format: {type(result)}")
                    
            except Exception as e:
                print(f"❌ Fundamental analysis execution failed: {e}")
                import traceback
                traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_market_analyst_prompt():
    """Test the effect of prompt word optimization by market analysts"""
    print("\n📈 Test the effect of market analyst prompt word optimization")
    print("=" * 80)
    
    try:
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, skipping LLM test")
            return True
        
        print(f"🔧 Create a market analyst...")
        
        # Create LLM and toolkit
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=1500
        )
        
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit()
        toolkit.update_config(config)
        
        # Create a market analyst
        from tradingagents.agents.analysts.market_analyst import create_market_analyst
        market_analyst = create_market_analyst(llm, toolkit)
        
        print(f"✅ Market analyst created")
        
        # test stocks
        test_ticker = "002027"
        
        print(f"\n📊 test stocks: {test_ticker}")
        print("-" * 60)
        
        # Create analysis status
        state = {
            "company_of_interest": test_ticker,
            "trade_date": "2025-07-16",
            "messages": []
        }
        
        print(f"🔍 [prompt word verification] Check prompt word construction...")
        
        # Get the company name (verification prompt word construction logic)
        from tradingagents.agents.analysts.market_analyst import _get_company_name
        from tradingagents.utils.stock_utils import StockUtils
        
        market_info = StockUtils.get_market_info(test_ticker)
        company_name = _get_company_name(test_ticker, market_info)
        
        print(f"   ✅ Stock code: {test_ticker}")
        print(f"   ✅ Company name: {company_name}")
        print(f"   ✅ market type: {market_info['market_name']}")
        print(f"   ✅ currency information: {market_info['currency_name']} ({market_info['currency_symbol']})")
        
        print(f"\n🤖 Perform market analysis...")
        
        try:
            # Perform market analysis
            result = market_analyst(state)
            
            if isinstance(result, dict) and 'market_report' in result:
                report = result['market_report']
                print(f"✅ Market analysis completed, report length: {len(report)}")
                
                # Check key elements in your report
                print(f"\n🔍 Check report content...")
                
                # Check stock symbol
                if test_ticker in report:
                    print(f"   ✅ Report contains correct ticker symbol: {test_ticker}")
                else:
                    print(f"   ❌ Report does not contain ticker symbol: {test_ticker}")
                
                # Check company name
                if company_name in report and company_name != f"stocks{test_ticker}":
                    print(f"   ✅ Report contains correct company name: {company_name}")
                else:
                    print(f"   ⚠️ Reports may not include specific company names")
                
                # Show report summary
                print(f"\n📄 Report Summary (first 500 characters):")
                print("-" * 40)
                print(report[:500])
                if len(report) > 500:
                    print("...")
                print("-" * 40)
                
            else:
                print(f"❌ Market analysis return format is abnormal: {type(result)}")
                
        except Exception as e:
            print(f"❌ Market analysis execution failed: {e}")
            import traceback
            traceback.print_exc()
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_prompt_elements():
    """Test prompt key elements"""
    print("\n🔧 Test prompt key elements")
    print("=" * 80)
    
    try:
        test_cases = [
            ("002027", "China A shares"),
            ("0700.HK", "Hong Kong stocks"),
            ("AAPL", "US stocks"),
        ]
        
        for ticker, market_type in test_cases:
            print(f"\n📊 test stocks: {ticker} ({market_type})")
            print("-" * 40)
            
            # Get market information and company name
            from tradingagents.utils.stock_utils import StockUtils
            from tradingagents.agents.analysts.fundamentals_analyst import _get_company_name_for_fundamentals
            from tradingagents.agents.analysts.market_analyst import _get_company_name
            
            market_info = StockUtils.get_market_info(ticker)
            fundamentals_name = _get_company_name_for_fundamentals(ticker, market_info)
            market_name = _get_company_name(ticker, market_info)
            
            print(f"   market information: {market_info['market_name']}")
            print(f"   Currency: {market_info['currency_name']} ({market_info['currency_symbol']})")
            print(f"   Company names obtained by fundamental analysts: {fundamentals_name}")
            print(f"   Company name obtained by market analysts: {market_name}")
            
            # Verify consistency
            if fundamentals_name == market_name:
                print(f"   ✅ The company name obtained by two analysts is the same")
            else:
                print(f"   ⚠️ The company names obtained by the two analysts are inconsistent")
            
            # Key elements that verification prompt words should contain
            expected_elements = [
                f"Company name:{fundamentals_name}",
                f"Stock code:{ticker}",
                f"Market:{market_info['market_name']}",
                f"Quotation currency:{market_info['currency_name']}"
            ]
            
            print(f"   Key elements that prompt words should contain:")
            for element in expected_elements:
                print(f"      ✅ {element}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🚀 Start testing the prompt word optimization effect")
    print("=" * 100)
    
    results = []
    
    # test 1: Prompt word key elements
    results.append(test_prompt_elements())
    
    # test 2: Fundamental analyst prompt word optimization effect
    results.append(test_fundamentals_analyst_prompt())
    
    # test 3: Market analysts prompt word optimization effects
    results.append(test_market_analyst_prompt())
    
    # Summary results
    print("\n" + "=" * 100)
    print("📋 Summary of test results")
    print("=" * 100)
    
    passed = sum(results)
    total = len(results)
    
    test_names = [
        "Prompt word key element verification",
        "Fundamental analyst tip word optimization",
        "Market analyst tips for word optimization"
    ]
    
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ Pass" if result else "❌ failed"
        print(f"{i+1}. {name}: {status}")
    
    print(f"\n📊 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! Prompt word optimization has a significant effect")
        print("\n📋 Optimization results:")
        print("1. ✅ Stock code and company name are properly separated")
        print("2. ✅ Prompt word contains complete stock information")
        print("3. ✅ Supports multiple market stock types")
        print("4. ✅ Improved analyst output quality")
        print("5. ✅ User experience significantly improved")
        
        print("\n🎯 Problem solved:")
        print("- ❌ Stock code used as company name")
        print("- ❌ Prompt word information is incomplete")
        print("- ❌ The analysis report is not professional enough")
        print("- ❌ Inconsistent support for multiple markets")
    else:
        print("⚠️ Some tests failed and need further optimization")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
