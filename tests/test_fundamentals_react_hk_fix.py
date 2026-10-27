"""
Testing fundamental analyst s ReAct model for Hong Kong stock repair
"""

import sys
import os

# Add project root directory to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def test_react_fundamentals_hk_config():
    """Test the ReAct model and fundamental analysts Hong Kong stock allocation"""
    print("🧪 Test the ReAct model and fundamental analysts Hong Kong stock allocation...")
    
    try:
        # Read fundamental analyst files
        with open('tradingagents/agents/analysts/fundamentals_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check ReAct mode Hong Kong stock configuration
        has_hk_react_branch = 'elif is_hk:' in content and 'ReAct Agent Analyze Hong Kong stocks' in content
        has_hk_stock_data_tool = 'HKStockDataTool' in content
        has_hk_fundamentals_tool = 'HKFundamentalsTool' in content
        has_hk_unified_call = 'get_hk_stock_data_unified' in content
        has_hk_info_call = 'get_hk_stock_info_unified' in content
        
        print(f"  Hong Kong Stock ReAct Branch: {has_hk_react_branch}")
        print(f"  Hong Kong stock data tools: {has_hk_stock_data_tool}")
        print(f"  Hong Kong Stock Fundamental Tools: {has_hk_fundamentals_tool}")
        print(f"  Hong Kong stock unified data call: {has_hk_unified_call}")
        print(f"  Hong Kong stock information call: {has_hk_info_call}")
        
        if all([has_hk_react_branch, has_hk_stock_data_tool, has_hk_fundamentals_tool, 
                has_hk_unified_call, has_hk_info_call]):
            print("  ✅ ReAct Model fundamental analysts have the correct allocation of Hong Kong stocks")
            return True
        else:
            print("  ❌ ReAct Model fundamental analyst s Hong Kong stock allocation is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ ReAct Model fundamental analyst s Hong Kong stock allocation test failed: {e}")
        return False

def test_us_stock_separation():
    """Testing the separation of US and Hong Kong stocks"""
    print("\n🧪 Testing the separation of US and Hong Kong stocks...")
    
    try:
        # Read fundamental analyst files
        with open('tradingagents/agents/analysts/fundamentals_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check US stocks tool no longer handles Hong Kong stocks
        us_fundamentals_desc = 'description: str = f"Get US stocks{ticker}fundamental data'
        no_hk_in_us_desc = 'US stocks/Hong Kong stocks' not in content.split('USFundamentalsTool')[1].split('def _run')[0]
        
        print(f"  The description of the US stock instrument is correct: {us_fundamentals_desc in content}")
        print(f"  US stock instruments do not include Hong Kong stocks: {no_hk_in_us_desc}")
        
        if us_fundamentals_desc in content and no_hk_in_us_desc:
            print("  ✅ The separation of US and Hong Kong stocks is correct")
            return True
        else:
            print("  ❌ The separation of US and Hong Kong stocks is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ The separation test of US and Hong Kong stocks failed: {e}")
        return False

def test_hk_query_format():
    """Test Hong Kong stock query format"""
    print("\n🧪 Test Hong Kong stock query format...")
    
    try:
        # Read fundamental analyst files
        with open('tradingagents/agents/analysts/fundamentals_analyst.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check the Hong Kong stock inquiry format
        has_hk_query = 'Please comment on Hong Kong stocks{ticker}Conduct detailed fundamental analysis' in content
        has_hk_currency = 'Prices are in Hong Kong dollars(HK$)Pricing' in content
        has_hk_features = 'T+0 Transactions, Hong Kong Dollar Exchange Rate' in content
        has_hk_format = '🇭🇰 Basic information of Hong Kong stocks' in content
        
        print(f"  Hong Kong stock inquiry format: {has_hk_query}")
        print(f"  Hong Kong dollar pricing instructions: {has_hk_currency}")
        print(f"  Explanation of characteristics of Hong Kong stocks: {has_hk_features}")
        print(f"  Hong Kong stock report format: {has_hk_format}")
        
        if all([has_hk_query, has_hk_currency, has_hk_features, has_hk_format]):
            print("  ✅ Hong Kong stock query format is correct")
            return True
        else:
            print("  ❌ Hong Kong stock query format is incomplete")
            return False
        
    except Exception as e:
        print(f"❌ Hong Kong stock query format test failed: {e}")
        return False

def test_toolkit_method_usage():
    """Test toolkit method usage"""
    print("\n🧪 Test toolkit method usage...")
    
    try:
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # How to check Hong Kong stocks
        has_hk_method = hasattr(toolkit, 'get_hk_stock_data_unified')
        
        print(f"  Toolkit Hong Kong Stock Method: {has_hk_method}")
        
        if has_hk_method:
            # Check if the method is callable
            method = getattr(toolkit, 'get_hk_stock_data_unified')
            is_callable = callable(method)
            print(f"  method callable: {is_callable}")
            
            if is_callable:
                print("  ✅ Use the toolkit method correctly")
                return True
            else:
                print("  ❌ Toolkit method is not callable")
                return False
        else:
            print("  ❌ The toolkit Hong Kong stock method does not exist")
            return False
        
    except Exception as e:
        print(f"❌ Toolkit method usage test fails: {e}")
        return False

def test_stock_type_detection():
    """Test stock type detection"""
    print("\n🧪 Test stock type detection...")
    
    try:
        from tradingagents.utils.stock_utils import StockUtils
        
        # Test Hong Kong Stock Testing
        hk_stocks = ["0700.HK", "9988.HK", "3690.HK"]
        us_stocks = ["AAPL", "TSLA", "MSFT"]
        china_stocks = ["000001", "600036", "300001"]
        
        print("  Hong Kong stock testing:")
        for stock in hk_stocks:
            market_info = StockUtils.get_market_info(stock)
            is_hk = market_info['is_hk']
            print(f"    {stock}: {is_hk} ({'✅' if is_hk else '❌'})")
            if not is_hk:
                return False
        
        print("  US stock testing:")
        for stock in us_stocks:
            market_info = StockUtils.get_market_info(stock)
            is_us = market_info['is_us']
            print(f"    {stock}: {is_us} ({'✅' if is_us else '❌'})")
            if not is_us:
                return False
        
        print("  A Stock detection:")
        for stock in china_stocks:
            market_info = StockUtils.get_market_info(stock)
            is_china = market_info['is_china']
            print(f"    {stock}: {is_china} ({'✅' if is_china else '❌'})")
            if not is_china:
                return False
        
        print("  ✅ Stock type detected correctly")
        return True
        
    except Exception as e:
        print(f"❌ Stock type detection test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 Fundamental analyst ReAct model Hong Kong stock repair test")
    print("=" * 60)
    
    tests = [
        test_react_fundamentals_hk_config,
        test_us_stock_separation,
        test_hk_query_format,
        test_toolkit_method_usage,
        test_stock_type_detection
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 60)
    print(f"🔧 Fundamental analyst ReAct model Hong Kong stock repair test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 Fundamental analyst s ReAct model of Hong Kong stocks has been repaired successfully!")
        print("\n✅ Repair summary:")
        print("  - ReAct The mode adds a dedicated branch for Hong Kong stocks")
        print("  - Hong Kong stocks use HKStockDataTool and HKFundamentalsTool")
        print("  - Hong Kong stocks give priority to using AKShare data source")
        print("  - The processing of U.S. stocks and Hong Kong stocks are completely separated")
        print("  - Hong Kong stock inquiry format includes Hong Kong dollar pricing and market characteristics")
        print("\n🚀 Hong Kong stock fundamental analysis will now use the correct data source!")
    else:
        print("⚠️ Some tests failed, please check the failed tests")

if __name__ == "__main__":
    main()
