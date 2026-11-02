# -*- coding: utf-8 -*-
"""
Simplified version of AKShare Hong Kong stock interface test
"""
import sys
import akshare as ak
import pandas as pd
from datetime import datetime

# Set output encoding
sys.stdout.reconfigure(encoding='utf-8')

def test_stock_hk_spot():
    """Test the real-time market situation of Hong Kong stocks on Sina Finance"""
    print("\n" + "="*80)
    print("test interface: stock_hk_spot (Sina Finance)")
    print("="*80)
    
    try:
        df = ak.stock_hk_spot()
        print(f"success! Return {len(df)} Only Hong Kong stocks")
        print(f"List: {list(df.columns)}")
        
        # Find Tencent Holdings
        test_symbol = "00700"
        matched = df[df['code'] == test_symbol]
        if not matched.empty:
            print(f"\n found {test_symbol} (Tencent Holdings):")
            print(matched.to_string())
        
        print(f"\n Top 5 stocks:")
        print(df.head(5)[['code', 'Chinese name', 'latest price', 'Increase or decrease']].to_string())
        
        return True, df
    except Exception as e:
        print(f"failed: {e}")
        return False, None


def test_stock_hk_daily():
    """Test Sina Finance Hong Kong stock market history"""
    print("\n" + "="*80)
    print("test interface: stock_hk_daily (Sina Finance)")
    print("="*80)
    
    try:
        test_symbol = "00700"
        df = ak.stock_hk_daily(symbol=test_symbol, adjust="qfq")
        print(f"success! Return {len(df)} pieces of historical data")
        print(f"List: {list(df.columns)}")
        
        print(f"\n Last 5 trading days:")
        print(df.tail(5).to_string())
        
        return True, df
    except Exception as e:
        print(f"failed: {e}")
        return False, None


def test_stock_hk_spot_em():
    """Test the real-time market conditions of Oriental Fortune Hong Kong stocks"""
    print("\n" + "="*80)
    print("test interface: stock_hk_spot_em (Oriental Fortune)")
    print("="*80)
    
    try:
        df = ak.stock_hk_spot_em()
        print(f"success! Return {len(df)} Only Hong Kong stocks")
        print(f"List: {list(df.columns)}")
        
        # Find Tencent Holdings
        test_symbol = "00700"
        matched = df[df['code'] == test_symbol]
        if not matched.empty:
            print(f"\n found {test_symbol} (Tencent Holdings):")
            print(matched.to_string())
        
        print(f"\n Top 5 stocks:")
        print(df.head(5)[['code', 'Name', 'latest price', 'Increase or decrease']].to_string())
        
        return True, df
    except Exception as e:
        print(f"failed: {e}")
        return False, None


def test_stock_individual_info_hk():
    """Test Snowball Hong Kong stock information"""
    print("\n" + "="*80)
    print("test interface: stock_individual_basic_info_hk_xq (snowball)")
    print("="*80)
    
    try:
        test_symbol = "00700"
        result = ak.stock_individual_basic_info_hk_xq(symbol=test_symbol)
        print(f"success! Return type: {type(result)}")
        print(f"data: {result}")
        
        return True, result
    except AttributeError:
        print("interface does not exist")
        return False, None
    except Exception as e:
        print(f"failed: {e}")
        return False, None


def main():
    """Main test function"""
    print("="*80)
    print("AKShare Hong Kong stock interface test")
    print(f"Test time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = {}
    
    # Test each interface
    results['stock_hk_spot'] = test_stock_hk_spot()
    results['stock_hk_daily'] = test_stock_hk_daily()
    results['stock_hk_spot_em'] = test_stock_hk_spot_em()
    results['stock_individual_basic_info_hk_xq'] = test_stock_individual_info_hk()
    
    # Summary
    print("\n" + "="*80)
    print("Test summary")
    print("="*80)
    
    for api_name, (success, _) in results.items():
        status = "success" if success else "failed"
        print(f"{api_name}: {status}")
    
    print("\n Recommended:")
    print("1. stock_hk_spot - Sina Finance real-time quotes (Get a list of stocks+real time price)")
    print("2. stock_hk_daily - Sina Finance Historical Quotes (Get K-line data)")
    print("3. stock_hk_spot_em - Oriental Fortune real-time quotes (Spare)")


if __name__ == "__main__":
    main()

