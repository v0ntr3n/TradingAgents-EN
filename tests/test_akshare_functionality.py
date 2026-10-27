#!/usr/bin/env python3
"""
AKShare Functional check test
Check the availability and functional completeness of AKShare in the current branch
"""

import sys
import os
import traceback
from typing import Dict, Any, List

def test_akshare_import():
    """Test AKShare library import"""
    print("🔍 Test AKShare library import...")
    try:
        import akshare as ak
        print(f"✅ AKShare Import successful, version: {ak.__version__}")
        return True, ak
    except ImportError as e:
        print(f"❌ AKShare Import failed: {e}")
        return False, None

def test_data_source_manager():
    """Testing AKShare support in Data Source Manager"""
    print("\n🔍 Test data source manager...")
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Check if AKShare is in enumeration
        akshare_enum = ChinaDataSource.AKSHARE
        print(f"✅ AKShare enumeration exists: {akshare_enum.value}")
        
        # Initialize the data source manager
        manager = DataSourceManager()
        
        # Check if AKShare is in available data sources
        available_sources = [s.value for s in manager.available_sources]
        if 'akshare' in available_sources:
            print("✅ AKShare In the list of available data sources")
        else:
            print("⚠️ AKShare Not in the list of available data sources")
        
        return True, manager
    except Exception as e:
        print(f"❌ Data source manager test failed: {e}")
        traceback.print_exc()
        return False, None

def test_akshare_adapter():
    """Test the AKShare adapter"""
    print("\n🔍 Test the AKShare adapter...")
    try:
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        manager = DataSourceManager()
        
        # Try to get AKShare adapter
        akshare_adapter = manager._get_akshare_adapter()
        
        if akshare_adapter is not None:
            print("✅ AKShare Adapter obtained successfully")
            return True, akshare_adapter
        else:
            print("❌ AKShare Adapter acquisition failed")
            return False, None
            
    except Exception as e:
        print(f"❌ AKShare Adapter test failed: {e}")
        traceback.print_exc()
        return False, None

def test_akshare_utils_file():
    """Check if akshare_utils.py file exists"""
    print("\n🔍 Check akshare_utils.py file...")
    
    akshare_utils_path = "tradingagents/dataflows/akshare_utils.py"
    
    if os.path.exists(akshare_utils_path):
        print(f"✅ Find the AKShare tool file: {akshare_utils_path}")
        
        try:
            from tradingagents.dataflows.akshare_utils import get_akshare_provider
            print("✅ get_akshare_provider Function imported successfully")
            return True
        except ImportError as e:
            print(f"❌ Import get_akshare_provider failed: {e}")
            return False
    else:
        print(f"❌ AKShare Tool file does not exist: {akshare_utils_path}")
        return False

def test_akshare_basic_functionality():
    """Test AKShare basic functions"""
    print("\n🔍 Test AKShare basic functions...")
    
    success, ak = test_akshare_import()
    if not success:
        return False
    
    try:
        # Test to get the stock list
        print("📊 Test to obtain the A-share stock list...")
        stock_list = ak.stock_info_a_code_name()
        if stock_list is not None and not stock_list.empty:
            print(f"✅ Obtained stock list successfully, total{len(stock_list)}only stocks")
            print(f"   Example: {stock_list.head(3).to_dict('records')}")
        else:
            print("❌ Failed to get stock list")
            return False
        
        # Test to obtain stock historical data
        print("\n📈 Test to obtain stock historical data...")
        stock_data = ak.stock_zh_a_hist(symbol="000001", period="daily", start_date="20241201", end_date="20241210", adjust="")
        if stock_data is not None and not stock_data.empty:
            print(f"✅ Obtaining stock data successfully, total{len(stock_data)}records")
            print(f"   latest data: {stock_data.tail(1).to_dict('records')}")
        else:
            print("❌ Failed to get stock data")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ AKShare Basic functional test failed: {e}")
        traceback.print_exc()
        return False

def test_data_source_switching():
    """Test data source switching function"""
    print("\n🔍 Test data source switching function...")
    
    try:
        from tradingagents.dataflows.interface import switch_china_data_source
        
        # Try switching to AKShare
        result = switch_china_data_source("akshare")
        print(f"Switch results: {result}")
        
        if "success" in result or "✅" in result:
            print("✅ Data source switched to AKShare successfully")
            return True
        else:
            print("❌ Failed to switch data source to AKShare")
            return False
            
    except Exception as e:
        print(f"❌ Data source switching test failed: {e}")
        traceback.print_exc()
        return False

def test_unified_data_interface():
    """Test unified data interface"""
    print("\n🔍 Test unified data interface...")
    
    try:
        from tradingagents.dataflows.interface import get_china_stock_data_unified
        
        # Set up the AKShare data source
        from tradingagents.dataflows.interface import switch_china_data_source
        switch_china_data_source("akshare")
        
        # Test to obtain stock data
        data = get_china_stock_data_unified("000001", "2024-12-01", "2024-12-10")
        
        if data and "Stock code" in data:
            print("✅ Unified data interface test successful")
            print(f"   Data preview: {data[:200]}...")
            return True
        else:
            print("❌ Unified data interface test failed")
            return False
            
    except Exception as e:
        print(f"❌ Unified data interface test failed: {e}")
        traceback.print_exc()
        return False

def create_missing_akshare_utils():
    """Create basic akshare_utils.py file if missing"""
    print("\n🔧 Check if you need to create akshare_utils.py...")
    
    akshare_utils_path = "tradingagents/dataflows/akshare_utils.py"
    
    if not os.path.exists(akshare_utils_path):
        print("📝 Create the basic akshare_utils.py file...")
        
        akshare_utils_content = '''#!/usr/bin/env python3
"""
AKShare Data source tools
Provides a unified interface for AKShare data acquisition
"""

import pandas as pd
from typing import Optional, Dict, Any
import warnings
warnings.filterwarnings('ignore')

class AKShareProvider:
    """AKShare data provider"""
    
    def __init__(self):
        """Initialize the AKShare provider"""
        try:
            import akshare as ak
            self.ak = ak
            self.connected = True
            print("✅ AKShare Initialization successful")
        except ImportError:
            self.ak = None
            self.connected = False
            print("❌ AKShare Not installed")
    
    def get_stock_data(self, symbol: str, start_date: str = None, end_date: str = None) -> Optional[pd.DataFrame]:
        """Get stock historical data"""
        if not self.connected:
            return None
        
        try:
            # Convert stock symbol format
            if len(symbol) == 6:
                symbol = symbol
            else:
                symbol = symbol.replace('.SZ', '').replace('.SS', '')
            
            # Get data
            data = self.ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.replace('-', '') if start_date else "20240101",
                end_date=end_date.replace('-', '') if end_date else "20241231",
                adjust=""
            )
            
            return data
            
        except Exception as e:
            print(f"❌ AKShare Failed to get stock data: {e}")
            return None
    
    def get_stock_info(self, symbol: str) -> Dict[str, Any]:
        """Get basic stock information"""
        if not self.connected:
            return {}
        
        try:
            # Get basic stock information
            stock_list = self.ak.stock_info_a_code_name()
            stock_info = stock_list[stock_list['code'] == symbol]
            
            if not stock_info.empty:
                return {
                    'symbol': symbol,
                    'name': stock_info.iloc[0]['name'],
                    'source': 'akshare'
                }
            else:
                return {'symbol': symbol, 'name': f'stocks{symbol}', 'source': 'akshare'}
                
        except Exception as e:
            print(f"❌ AKShare Failed to obtain stock information: {e}")
            return {'symbol': symbol, 'name': f'stocks{symbol}', 'source': 'akshare'}

def get_akshare_provider() -> AKShareProvider:
    """Get AKShare provider instance"""
    return AKShareProvider()
'''
        
        try:
            with open(akshare_utils_path, 'w', encoding='utf-8') as f:
                f.write(akshare_utils_content)
            print(f"✅ akshare_utils.py was created successfully: {akshare_utils_path}")
            return True
        except Exception as e:
            print(f"❌ Failed to create akshare_utils.py: {e}")
            return False
    else:
        print("✅ akshare_utils.py File already exists")
        return True

def main():
    """Main test function"""
    print("🔍 AKShare Functional integrity check")
    print("=" * 60)
    
    test_results = {}
    
    # 1. Test AKShare library import
    test_results['akshare_import'] = test_akshare_import()[0]
    
    # 2. Check akshare_utils.py file
    test_results['akshare_utils_file'] = test_akshare_utils_file()
    
    # 3. If the file does not exist, try to create it
    if not test_results['akshare_utils_file']:
        test_results['create_akshare_utils'] = create_missing_akshare_utils()
    
    # 4. Test data source manager
    test_results['data_source_manager'] = test_data_source_manager()[0]
    
    # 5. Test the AKShare adapter
    test_results['akshare_adapter'] = test_akshare_adapter()[0]
    
    # 6. Test AKShare basic functions
    test_results['akshare_basic'] = test_akshare_basic_functionality()
    
    # 7. Test data source switching
    test_results['data_source_switching'] = test_data_source_switching()
    
    # 8. Test unified data interface
    test_results['unified_interface'] = test_unified_data_interface()
    
    # Summary results
    print(f"\n📊 AKShare Functional check summary")
    print("=" * 60)
    
    passed = sum(test_results.values())
    total = len(test_results)
    
    for test_name, result in test_results.items():
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name:25} {status}")
    
    print(f"\n🎯 Overall results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 AKShare The functionality is fully functional!")
    elif passed >= total * 0.7:
        print("⚠️ AKShare The functionality is basically usable, but some issues need to be fixed")
    else:
        print("❌ AKShare There is a serious problem with the functionality and it needs to be fixed")
    
    return passed == total

if __name__ == "__main__":
    main()
