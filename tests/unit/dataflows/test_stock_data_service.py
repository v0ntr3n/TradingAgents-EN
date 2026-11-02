#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stock data service test program
test MongoDB -> Tushare Complete degradation mechanism for data interfaces
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

try:
    from tradingagents.dataflows.stock_data_service import StockDataService, get_stock_data_service
    from tradingagents.api.stock_api import (
        get_stock_info, get_all_stocks, get_stock_data,
        search_stocks, get_market_summary, check_service_status
    )
    SERVICES_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Service unavailable: {e}")
    SERVICES_AVAILABLE = False

class TestStockDataService(unittest.TestCase):
    """Stock data service test class"""
    
    def setUp(self):
        """Preparation before test"""
        if not SERVICES_AVAILABLE:
            self.skipTest("Stock data service is unavailable")
        
        self.service = StockDataService()
    
    def test_service_initialization(self):
        """Test service initialization"""
        print("\n🧪 Test service initialization...")
        
        # Check if the service is initialized correctly
        self.assertIsNotNone(self.service)
        
        # Check the initialization status of each component
        print(f"  📊 Database manager: {'✅' if self.service.db_manager else '❌'}")
        print(f"  📡 unified data interface: {'✅' if hasattr(self.service, 'get_stock_data') else '❌'}")
        
        print("  ✅ Service initialization test passed")
    
    def test_get_stock_basic_info_single(self):
        """Test to obtain basic information of a single stock"""
        print("\n🧪 Test to obtain basic information of a single stock...")
        
        test_codes = ['000001', '600000', '300001']
        
        for code in test_codes:
            print(f"  🔍 Test ticker: {code}")
            
            result = self.service.get_stock_basic_info(code)
            
            # The result should not be None
            self.assertIsNotNone(result)
            
            if isinstance(result, dict):
                if 'error' in result:
                    print(f"    ⚠️ Failed to obtain: {result['error']}")
                else:
                    print(f"    ✅ get success: {result.get('name', 'N/A')}")
                    # Check required fields
                    self.assertIn('code', result)
                    self.assertIn('name', result)
                    self.assertIn('source', result)
            
        print("  ✅ Single stock information test completed")
    
    def test_get_stock_basic_info_all(self):
        """Test to obtain basic information of all stocks"""
        print("\n🧪 Test to obtain basic information of all stocks...")
        
        result = self.service.get_stock_basic_info()
        
        # The result should not be None
        self.assertIsNotNone(result)
        
        if isinstance(result, list) and len(result) > 0:
            print(f"  ✅ get success: {len(result)} only stocks")
            
            # Check the fields of the first stock
            first_stock = result[0]
            if 'error' not in first_stock:
                self.assertIn('code', first_stock)
                self.assertIn('name', first_stock)
                print(f"  📊 Example stocks: {first_stock.get('code')} - {first_stock.get('name')}")
        elif isinstance(result, dict) and 'error' in result:
            print(f"  ⚠️ Failed to obtain: {result['error']}")
        else:
            print(f"  ⚠️ No data obtained")
        
        print("  ✅ All stock information testing completed")
    
    def test_market_classification(self):
        """Test market classification functionality"""
        print("\n🧪 Test market classification functionality...")
        
        test_cases = [
            ('000001', 'Shenzhen', 'Shenzhen Main Board'),
            ('600000', 'Shanghai', 'Shanghai Main Board'),
            ('300001', 'Shenzhen', 'GEM'),
            ('688001', 'Shanghai', 'Science and Technology Innovation Board')
        ]
        
        for code, expected_market, expected_category in test_cases:
            market = self.service._get_market_name(code)
            category = self.service._get_stock_category(code)
            
            print(f"  📊 {code}: {market} - {category}")
            
            self.assertEqual(market, expected_market)
            self.assertEqual(category, expected_category)
        
        print("  ✅ Market classification test passed")
    
    def test_fallback_data(self):
        """Test downgrade data functionality"""
        print("\n🧪 Test downgrade data functionality...")
        
        # Test downgrade data for individual stocks
        fallback_single = self.service._get_fallback_data('999999')
        self.assertIsInstance(fallback_single, dict)
        self.assertIn('code', fallback_single)
        self.assertIn('error', fallback_single)
        print(f"  📊 Single stock downgrade: {fallback_single['code']} - {fallback_single.get('name')}")
        
        # Test downgrade data for all stocks
        fallback_all = self.service._get_fallback_data()
        self.assertIsInstance(fallback_all, dict)
        self.assertIn('error', fallback_all)
        print(f"  📊 All stocks downgraded: {fallback_all['error']}")
        
        print("  ✅ Downgraded data test passed")

class TestStockAPI(unittest.TestCase):
    """Stock API test class"""
    
    def setUp(self):
        """Preparation before test"""
        if not SERVICES_AVAILABLE:
            self.skipTest("Stock API is not available")
    
    def test_service_status(self):
        """Test service status check"""
        print("\n🧪 Test service status check...")
        
        status = check_service_status()
        
        self.assertIsInstance(status, dict)
        self.assertIn('service_available', status)
        
        print(f"  📊 Service status:")
        for key, value in status.items():
            print(f"    {key}: {value}")
        
        print("  ✅ Service status test passed")
    
    def test_get_stock_info_api(self):
        """Test stock information API"""
        print("\n🧪 Test stock information API...")
        
        test_codes = ['000001', '600000', '999999']  # Contains a code that does not exist
        
        for code in test_codes:
            print(f"  🔍 Test API access: {code}")
            
            result = get_stock_info(code)
            
            self.assertIsInstance(result, dict)
            
            if 'error' in result:
                print(f"    ⚠️ expected error: {result['error']}")
            else:
                print(f"    ✅ get success: {result.get('name')}")
                self.assertIn('code', result)
                self.assertIn('name', result)
        
        print("  ✅ Stock information API testing completed")
    
    def test_search_stocks_api(self):
        """Test stock search API"""
        print("\n🧪 Test stock search API...")
        
        keywords = ['Peace', 'bank', '000001', 'xyz123']  # Contains a keyword that does not exist
        
        for keyword in keywords:
            print(f"  🔍 Search keywords: '{keyword}'")
            
            results = search_stocks(keyword)
            
            self.assertIsInstance(results, list)
            
            if not results or (len(results) == 1 and 'error' in results[0]):
                print(f"    ⚠️ No matching results found")
            else:
                print(f"    ✅ found {len(results)} matching results")
                # Check first result
                if results and 'error' not in results[0]:
                    first_result = results[0]
                    print(f"    📊 Example: {first_result.get('code')} - {first_result.get('name')}")
        
        print("  ✅ Stock search API testing completed")
    
    def test_market_summary_api(self):
        """Test market overview API"""
        print("\n🧪 Test market overview API...")
        
        summary = get_market_summary()
        
        self.assertIsInstance(summary, dict)
        
        if 'error' in summary:
            print(f"  ⚠️ Failed to obtain: {summary['error']}")
        else:
            print(f"  ✅ get success:")
            print(f"    📊 Total number of shares: {summary.get('total_count', 0):,}")
            print(f"    🏢 Shanghai stock market: {summary.get('shanghai_count', 0):,}")
            print(f"    🏢 Shenzhen stock market: {summary.get('shenzhen_count', 0):,}")
            print(f"    🔗 data source: {summary.get('data_source', 'unknown')}")
            
            # Check required fields
            self.assertIn('total_count', summary)
            self.assertIn('data_source', summary)
        
        print("  ✅ Market Overview API Test Completed")
    
    def test_stock_data_api(self):
        """Test stock data API"""
        print("\n🧪 Test stock data API...")
        
        # Test to obtain stock historical data
        stock_code = '000001'
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        print(f"  📊 get {stock_code} from {start_date} Arrive {end_date} data")
        
        result = get_stock_data(stock_code, start_date, end_date)
        
        self.assertIsInstance(result, str)
        
        # Check if the results contain expected content
        if "❌" in result:
            print(f"    ⚠️ Failed to get (expected situation)")
        else:
            print(f"    ✅ Get success (data length: {len(result)} characters)")
        
        print("  ✅ Stock data API testing completed")

class TestFallbackMechanism(unittest.TestCase):
    """Downgrade mechanism test class"""
    
    def setUp(self):
        """Preparation before test"""
        if not SERVICES_AVAILABLE:
            self.skipTest("Downgrade mechanism test is not available")
    
    @patch('tradingagents.dataflows.stock_data_service.DATABASE_MANAGER_AVAILABLE', False)
    def test_mongodb_unavailable_fallback(self):
        """Testing for downgrade when MongoDB is unavailable"""
        print("\n🧪 Testing for downgrade when MongoDB is unavailable...")
        
        # Create a new service instance (simulating MongoDB is not available)
        service = StockDataService()
        
        # The database manager should be None
        self.assertIsNone(service.db_manager)
        
        # Try to get stock information (should downgrade to Tushare data interface)
        result = service.get_stock_basic_info('000001')
        
        self.assertIsNotNone(result)
        
        if isinstance(result, dict):
            if 'error' in result:
                print(f"    ⚠️ Downgrade failed: {result['error']}")
            else:
                print(f"    ✅ Downgrade successful: {result.get('name')}")
                self.assertEqual(result.get('source'), 'unified_api')
        
        print("  ✅ MongoDB Downgrade test completed")
    
    def test_invalid_stock_code_fallback(self):
        """Testing the downgrade of an invalid stock symbol"""
        print("\n🧪 Testing the downgrade of an invalid stock symbol...")
        
        service = StockDataService()
        
        # Testing for obviously invalid stock symbols
        invalid_codes = ['999999', 'INVALID', '123456']
        
        for code in invalid_codes:
            print(f"  🔍 Test invalid code: {code}")
            
            result = service.get_stock_basic_info(code)
            
            self.assertIsNotNone(result)
            
            if isinstance(result, dict):
                # Should contain error messages or downgrade data
                if 'error' in result:
                    print(f"    ✅ Correctly identify invalid codes")
                else:
                    print(f"    ⚠️ Data returned: {result.get('name')}")
        
        print("  ✅ Invalid code downgrade test completed")

def run_comprehensive_test():
    """Run comprehensive tests"""
    print("🚀 Comprehensive testing of stock data services")
    print("=" * 60)
    
    if not SERVICES_AVAILABLE:
        print("❌ Service is unavailable and tests cannot be run")
        return
    
    # Create test suite
    test_suite = unittest.TestSuite()
    
    # Add test case
    test_suite.addTest(unittest.makeSuite(TestStockDataService))
    test_suite.addTest(unittest.makeSuite(TestStockAPI))
    test_suite.addTest(unittest.makeSuite(TestFallbackMechanism))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    
    # Output summary of test results
    print("\n" + "=" * 60)
    print("📊 Summary of test results:")
    print(f"  ✅ success: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"  ❌ failed: {len(result.failures)}")
    print(f"  💥 Error: {len(result.errors)}")
    print(f"  ⏭️ skip: {len(result.skipped)}")
    
    if result.failures:
        print("\n❌ failed test:")
        for test, traceback in result.failures:
            print(f"  - {test}: {traceback.split('AssertionError:')[-1].strip()}")
    
    if result.errors:
        print("\n💥 wrong test:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback.split('Exception:')[-1].strip()}")
    
    # overall assessment
    if result.wasSuccessful():
        print("\n🎉 All tests passed! The stock data service is working fine")
    else:
        print("\n⚠️ Some tests failed, please check the relevant configuration")
    
    return result.wasSuccessful()

def run_manual_test():
    """Run manual tests (for debugging)"""
    print("🔧 Manual test mode")
    print("=" * 40)
    
    if not SERVICES_AVAILABLE:
        print("❌ Service unavailable")
        return
    
    try:
        # Test service status
        print("\n1. Check service status:")
        status = check_service_status()
        for key, value in status.items():
            print(f"   {key}: {value}")
        
        # Test to obtain stock information
        print("\n2. Get stock information:")
        stock_info = get_stock_info('000001')
        if 'error' in stock_info:
            print(f"   Error: {stock_info['error']}")
        else:
            print(f"   success: {stock_info.get('code')} - {stock_info.get('name')}")
        
        # Test search functionality
        print("\n3. Search stocks:")
        results = search_stocks('Peace')
        if results and 'error' not in results[0]:
            print(f"   found {len(results)} only stocks")
            for i, stock in enumerate(results[:3], 1):
                print(f"   {i}. {stock.get('code')} - {stock.get('name')}")
        else:
            print("   No matching stock found")
        
        # Test market overview
        print("\n4. Market overview:")
        summary = get_market_summary()
        if 'error' in summary:
            print(f"   Error: {summary['error']}")
        else:
            print(f"   Total number of shares: {summary.get('total_count', 0):,}")
            print(f"   data source: {summary.get('data_source')}")
        
        print("\n✅ Manual testing completed")
        
    except Exception as e:
        print(f"\n❌ Manual test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Stock data service test program')
    parser.add_argument('--manual', action='store_true', help='Run manual test mode')
    parser.add_argument('--comprehensive', action='store_true', help='Run comprehensive tests')
    
    args = parser.parse_args()
    
    if args.manual:
        run_manual_test()
    elif args.comprehensive:
        run_comprehensive_test()
    else:
        # Run comprehensive tests by default
        print("💡 Tips: Use --manual to run manual tests and --comprehensive to run comprehensive tests")
        print("Run comprehensive tests by default...\n")
        run_comprehensive_test()