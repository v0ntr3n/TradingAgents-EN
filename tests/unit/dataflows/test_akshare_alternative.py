#!/usr/bin/env python3
"""
Testing AKShare s alternative financial data interface
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import pandas as pd

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def test_akshare_individual_info():
    """Test AKShare s individual stock information interface"""
    print("=" * 60)
    print("🧪 Test AKShare s individual stock information interface")
    print("=" * 60)
    
    try:
        import akshare as ak
        
        # Test a few stocks
        test_symbols = ['000001', '600000', '000002']
        
        for symbol in test_symbols:
            print(f"\n📊 test stocks: {symbol}")
            try:
                data = ak.stock_individual_info_em(symbol=symbol)
                
                if data is not None and not data.empty:
                    print(f"✅ successfully obtained{symbol}information: {len(data)}records")
                    print(f"   data structure:")
                    for i, row in data.iterrows():
                        item = row.get('item', 'N/A')
                        value = row.get('value', 'N/A')
                        print(f"     {item}: {value}")
                else:
                    print(f"❌ Unable to obtain{symbol}information")
                    
            except Exception as e:
                print(f"❌ get{symbol}failed: {e}")
        
    except Exception as e:
        print(f"❌ test failed: {e}")

def test_akshare_financial_apis():
    """Test other financial related aspects of AKShare API"""
    print("\n" + "=" * 60)
    print("🧪 Test other financial related aspects of AKShare API")
    print("=" * 60)
    
    try:
        import akshare as ak
        
        # Test different finances API
        apis_to_test = [
            ('stock_zh_a_hist', 'Stock historical data'),
            ('stock_financial_abstract', 'financial summary'),
            ('stock_financial_analysis_indicator', 'financial analysis indicators'),
        ]
        
        test_symbol = '000001'
        
        for api_name, description in apis_to_test:
            print(f"\n📊 test {api_name} ({description}):")
            try:
                if api_name == 'stock_zh_a_hist':
                    # Get historical data
                    data = ak.stock_zh_a_hist(symbol=test_symbol, period="daily", start_date="20241201", end_date="20241205", adjust="")
                elif api_name == 'stock_financial_abstract':
                    # financial summary
                    data = ak.stock_financial_abstract(symbol=test_symbol)
                elif api_name == 'stock_financial_analysis_indicator':
                    # financial analysis indicators
                    data = ak.stock_financial_analysis_indicator(symbol=test_symbol)
                else:
                    continue
                
                if data is not None and not data.empty:
                    print(f"   ✅ success: {len(data)}records")
                    print(f"   List: {list(data.columns)}")
                    if len(data) > 0:
                        print(f"   sample data:")
                        print(data.head(2))
                else:
                    print(f"   ❌ No data")
                    
            except Exception as e:
                print(f"   ❌ failed: {e}")
        
    except Exception as e:
        print(f"❌ test failed: {e}")

def test_akshare_market_data():
    """Test AKShare s market data interface"""
    print("\n" + "=" * 60)
    print("🧪 Test AKShare s market data interface")
    print("=" * 60)
    
    try:
        import akshare as ak
        
        # test market related API
        apis_to_test = [
            ('stock_zh_index_spot', 'Index real-time data'),
            ('stock_zh_a_hist', 'Historical data of individual stocks'),
        ]
        
        for api_name, description in apis_to_test:
            print(f"\n📊 test {api_name} ({description}):")
            try:
                if api_name == 'stock_zh_index_spot':
                    # index data
                    data = ak.stock_zh_index_spot()
                elif api_name == 'stock_zh_a_hist':
                    # Historical data of individual stocks
                    data = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20241201", end_date="20241205", adjust="")
                else:
                    continue
                
                if data is not None and not data.empty:
                    print(f"   ✅ success: {len(data)}records")
                    print(f"   List: {list(data.columns)}")
                    if len(data) > 0:
                        print(f"   First 3 pieces of data:")
                        print(data.head(3))
                else:
                    print(f"   ❌ No data")
                    
            except Exception as e:
                print(f"   ❌ failed: {e}")
        
    except Exception as e:
        print(f"❌ test failed: {e}")

if __name__ == "__main__":
    test_akshare_individual_info()
    test_akshare_financial_apis()
    test_akshare_market_data()
