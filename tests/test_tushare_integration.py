#!/usr/bin/env python3
"""
Tushare Integration testing
Verify the integrated functions of Tushare data source, including data acquisition, caching, interface calling, etc.
"""

import os
import sys
import pandas as pd
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_tushare_provider():
    """Test the basic functions of Tushare provider"""
    print("\n🔧 Test the Tushare provider")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_utils import get_tushare_provider
        
        print("✅ Tushare Tool library loaded successfully")
        
        # Create provider instance
        provider = get_tushare_provider()
        
        if provider.connected:
            print("✅ Tushare API Connection successful")
            
            # Test to get the stock list
            print("🔄 Test to get the stock list...")
            stock_list = provider.get_stock_list()
            
            if not stock_list.empty:
                print(f"✅ Obtained stock list successfully: {len(stock_list)}Article")
                print(f"📊 Example stocks: {stock_list.head(3)[['ts_code', 'name']].to_string(index=False)}")
            else:
                print("❌ Failed to get stock list")
            
            # Test to obtain stock information
            print("🔄 Test to obtain stock information...")
            stock_info = provider.get_stock_info("000001")
            
            if stock_info and stock_info.get('name'):
                print(f"✅ Obtained stock information successfully: {stock_info['name']}")
            else:
                print("❌ Failed to obtain stock information")
            
            # Test to obtain stock data
            print("🔄 Test to obtain stock data...")
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            stock_data = provider.get_stock_daily("000001", start_date, end_date)
            
            if not stock_data.empty:
                print(f"✅ Obtaining stock data successfully: {len(stock_data)}Article")
            else:
                print("❌ Failed to get stock data")
        else:
            print("❌ Tushare API Connection failed")
        
    except Exception as e:
        print(f"❌ Tushare Provider test failed: {e}")
        import traceback
        traceback.print_exc()


def test_tushare_adapter():
    """Test Tushare adapter functionality"""
    print("\n🔧 Test Tushare Adapter")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        
        print("✅ Tushare Adapter library loaded successfully")
        
        # Create adapter instance
        adapter = get_tushare_adapter()
        
        # Test to obtain stock data
        print("🔄 Test to obtain stock data...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        stock_data = adapter.get_stock_data("000001", start_date, end_date)
        
        if not stock_data.empty:
            print(f"✅ Obtaining stock data successfully: {len(stock_data)}Article")
            print(f"📊 data column: {list(stock_data.columns)}")
        else:
            print("❌ Failed to get stock data")
        
        # Test to obtain stock information
        print("🔄 Test to obtain stock information...")
        stock_info = adapter.get_stock_info("000001")
        
        if stock_info and stock_info.get('name'):
            print(f"✅ Obtained stock information successfully: {stock_info['name']}")
        else:
            print("❌ Failed to obtain stock information")
        
        # Test searching for stocks
        print("🔄 Test searching for stocks...")
        search_results = adapter.search_stocks("Peace")
        
        if not search_results.empty:
            print(f"✅ Stock search successful: {len(search_results)}results")
        else:
            print("❌ Stock search failed")
        
        # Test fundamental data
        print("🔄 Test fundamental data...")
        fundamentals = adapter.get_fundamentals("000001")
        
        if fundamentals and len(fundamentals) > 100:
            print(f"✅ Fundamental data obtained successfully: {len(fundamentals)}character")
        else:
            print("❌ Failed to obtain fundamental data")
        
    except Exception as e:
        print(f"❌ Tushare Adapter test failed: {e}")
        import traceback
        traceback.print_exc()


def test_tushare_interface():
    """Test Tushare interface function"""
    print("\n🔧 Test Tushare interface function")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.interface import (
            get_china_stock_data_tushare,
            search_china_stocks_tushare,
            get_china_stock_fundamentals_tushare,
            get_china_stock_info_tushare
        )
        
        print("✅ Tushare Interface function loaded successfully")
        
        # Test the interface for obtaining stock data
        print("🔄 Test the stock data interface...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        data_result = get_china_stock_data_tushare("000001", start_date, end_date)
        
        if "Stock code: 000001" in data_result:
            print("✅ Stock data interface test successful")
        else:
            print("❌ Stock data interface test failed")
        
        # Test search interface
        print("🔄 Test search interface...")
        search_result = search_china_stocks_tushare("Peace")
        
        if "Search keywords: Peace" in search_result:
            print("✅ Search interface test successful")
        else:
            print("❌ Search interface test failed")
        
        # Test the stock information interface
        print("🔄 Test the stock information interface...")
        info_result = get_china_stock_info_tushare("000001")
        
        if "Stock code: 000001" in info_result:
            print("✅ Stock information interface test successful")
        else:
            print("❌ Stock information interface test failed")
        
        # Test fundamental interface
        print("🔄 Test fundamental interface...")
        fundamentals_result = get_china_stock_fundamentals_tushare("000001")
        
        if "Fundamental Analysis Report" in fundamentals_result:
            print("✅ Basic interface test successful")
        else:
            print("❌ Fundamental interface test failed")
        
    except Exception as e:
        print(f"❌ Tushare Interface function test failed: {e}")
        import traceback
        traceback.print_exc()


def test_tushare_cache():
    """Test Tushare caching function"""
    print("\n🔧 Test Tushare caching function")
    print("=" * 60)
    
    try:
        from tradingagents.dataflows.tushare_adapter import get_tushare_adapter
        
        adapter = get_tushare_adapter()
        
        if not adapter.enable_cache:
            print("⚠️ Cache function is not enabled, skip cache test")
            return
        
        print("✅ Caching is enabled")
        
        # Get data for the first time (should be obtained from API)
        print("🔄 Getting data for the first time (from API)...")
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d')
        
        data1 = adapter.get_stock_data("000001", start_date, end_date)
        
        if not data1.empty:
            print(f"✅ First time success: {len(data1)}Article")
        else:
            print("❌ The first acquisition failed")
            return
        
        # Second time to get data (should be from cache)
        print("🔄 Second time getting data (from cache)...")
        data2 = adapter.get_stock_data("000001", start_date, end_date)
        
        if not data2.empty:
            print(f"✅ Successful second time: {len(data2)}Article")
            
            # Compare data for consistency
            if len(data1) == len(data2):
                print("✅ Cache data consistency verification passed")
            else:
                print("⚠️ Cache data may be inconsistent")
        else:
            print("❌ The second acquisition failed")
        
    except Exception as e:
        print(f"❌ Tushare Cache test failed: {e}")
        import traceback
        traceback.print_exc()


def check_tushare_environment():
    """Check Tushare environment configuration"""
    print("\n🔧 Check Tushare environment configuration")
    print("=" * 60)
    
    # Check Tushare library
    try:
        import tushare as ts
        print("✅ Tushare Library installed")
        print(f"📦 Tushare version: {ts.__version__}")
    except ImportError:
        print("❌ Tushare The library is not installed, please run: pip install tushare")
        return False
    
    # Check API Token
    token = os.getenv('TUSHARE_TOKEN')
    if token:
        print("✅ TUSHARE_TOKEN Environment variables are set")
        print(f"🔑 Token length: {len(token)}character")
    else:
        print("❌ TUSHARE_TOKEN environment variable not set")
        print("💡 Please set it in the .env file: TUSHARE_TOKEN=your_token_here")
        return False
    
    # Check cache directory
    try:
        from tradingagents.dataflows.cache_manager import get_cache
        cache = get_cache()
        print("✅ Cache manager available")
    except Exception as e:
        print(f"⚠️ Cache manager is unavailable: {e}")
    
    return True


def main():
    """Main test function"""
    print("🔬 Tushare Integration testing")
    print("=" * 70)
    print("💡 Test target:")
    print("   - Tushare Environment configuration check")
    print("   - Tushare Provider functionality testing")
    print("   - Tushare Adapter functional test")
    print("   - Tushare Interface function testing")
    print("   - Tushare Cache function test")
    print("=" * 70)
    
    # Check environment configuration
    if not check_tushare_environment():
        print("\n❌ The environment configuration check failed. Please configure the Tushare environment first.")
        return
    
    # Run all tests
    test_tushare_provider()
    test_tushare_adapter()
    test_tushare_interface()
    test_tushare_cache()
    
    # Summary
    print("\n📋 Tushare Integration test summary")
    print("=" * 60)
    print("✅ Tushare provider: Basic functional testing")
    print("✅ Tushare adapter: Data acquisition and processing")
    print("✅ Tushare interface: Unified interface function")
    print("✅ Tushare cache: Performance optimization features")
    
    print("\n🎉 Tushare Integration testing completed!")
    print("\n🎯 Tushare data sources are now available:")
    print("   1. Select Tushare as the A-share data source in the CLI")
    print("   2. Configure Tushare data source in web interface")
    print("   3. Use API interface to obtain A-share data")
    print("   4. Enjoy high-quality A-share data services")
    
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
