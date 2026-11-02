#!/usr/bin/env python3
"""
Test data consistency check function
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import pandas as pd
from datetime import datetime, timedelta

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s'
)

def test_data_consistency_checker():
    """Test data consistency checker"""
    print("=" * 60)
    print("🧪 Test data consistency check function")
    print("=" * 60)
    
    try:
        from app.services.data_source_adapters import DataSourceManager
        from app.services.data_consistency_checker import DataConsistencyChecker
        
        # 1. Test data source manager initialization
        print("\n1. Initialize the data source manager...")
        manager = DataSourceManager()
        available_adapters = manager.get_available_adapters()
        
        print(f"✅ Available data sources: {[adapter.name for adapter in available_adapters]}")
        print(f"✅ consistency checker: {'Available' if manager.consistency_checker else 'Not available'}")
        
        if len(available_adapters) < 2:
            print("⚠️ At least 2 data sources are required for consistency checking")
            return
        
        # 2. Test to get data
        trade_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        print(f"\n2. get{trade_date}Data consistency check...")
        
        # Get data using consistency checks
        data, source, consistency_report = manager.get_daily_basic_with_consistency_check(trade_date)
        
        if data is not None and not data.empty:
            print(f"✅ Data obtained successfully: {len(data)}record, source: {source}")
            
            if consistency_report:
                print(f"\n📊 Consistency check report:")
                print(f"   data consistency: {'✅ consistent' if consistency_report['is_consistent'] else '❌ inconsistent'}")
                print(f"   confidence score: {consistency_report['confidence_score']:.2f}")
                print(f"   Recommended action: {consistency_report['recommended_action']}")
                print(f"   solution strategy: {consistency_report['resolution_strategy']}")
                print(f"   master data source: {consistency_report['primary_source']}")
                print(f"   secondary data source: {consistency_report['secondary_source']}")
                
                # Show specific differences
                if consistency_report['differences']:
                    print(f"\n📈 Metric difference details:")
                    for metric, diff_info in consistency_report['differences'].items():
                        if isinstance(diff_info, dict) and 'difference_pct' in diff_info:
                            print(f"   {metric}:")
                            print(f"     Primary data source value: {diff_info.get('primary_value', 'N/A')}")
                            print(f"     Secondary data source value: {diff_info.get('secondary_value', 'N/A')}")
                            if diff_info.get('difference_pct') is not None:
                                print(f"     Difference percentage: {diff_info['difference_pct']:.2%}")
                            print(f"     Is it significant?: {'Yes' if diff_info.get('is_significant') else 'No'}")
                            print(f"     Tolerance: {diff_info.get('tolerance', 0):.2%}")
            else:
                print("ℹ️ No consistency check is done (maybe only one data source is available)")
        else:
            print("❌ Failed to get data")
        
        # 3. Test a separate consistency checker
        print(f"\n3. Test standalone consistency checker...")
        
        if manager.consistency_checker and len(available_adapters) >= 2:
            # Get data from two data sources separately
            primary_adapter = available_adapters[0]
            secondary_adapter = available_adapters[1]
            
            primary_data = primary_adapter.get_daily_basic(trade_date)
            secondary_data = secondary_adapter.get_daily_basic(trade_date)
            
            if primary_data is not None and secondary_data is not None:
                consistency_result = manager.consistency_checker.check_daily_basic_consistency(
                    primary_data, secondary_data,
                    primary_adapter.name, secondary_adapter.name
                )
                
                print(f"✅ Independent consistency check completed:")
                print(f"   Consistency: {consistency_result.is_consistent}")
                print(f"   Confidence: {consistency_result.confidence_score:.2f}")
                print(f"   Recommended action: {consistency_result.recommended_action}")
                
                # Test conflict resolution
                final_data, strategy = manager.consistency_checker.resolve_data_conflicts(
                    primary_data, secondary_data, consistency_result
                )
                print(f"   solution strategy: {strategy}")
                print(f"   The final number of data items: {len(final_data) if final_data is not None else 0}")
            else:
                print("⚠️ Unable to obtain sufficient data for independent inspection")
        
        print(f"\n✅ Data consistency check test completed")
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

def test_mock_data_consistency():
    """Test consistency checking logic using mock data"""
    print("\n" + "=" * 60)
    print("🧪 Test consistency checking logic using mock data")
    print("=" * 60)
    
    try:
        from app.services.data_consistency_checker import DataConsistencyChecker
        
        checker = DataConsistencyChecker()
        
        # Create simulated data
        # Master data source data
        primary_data = pd.DataFrame({
            'ts_code': ['000001.SZ', '000002.SZ', '600000.SH'],
            'pe': [10.5, 15.2, 8.9],
            'pb': [1.2, 2.1, 0.9],
            'total_mv': [100000, 50000, 80000],
            'trade_date': ['20241201', '20241201', '20241201']
        })
        
        # Secondary data source data (slight differences)
        secondary_data = pd.DataFrame({
            'ts_code': ['000001.SZ', '000002.SZ', '600000.SH'],
            'pe': [10.8, 15.0, 9.1],  # slight difference
            'pb': [1.25, 2.0, 0.95],  # slight difference
            'total_mv': [101000, 49500, 81000],  # slight difference
            'trade_date': ['20241201', '20241201', '20241201']
        })
        
        print("📊 Simulation data creation completed:")
        print(f"   master data source: {len(primary_data)}records")
        print(f"   secondary data source: {len(secondary_data)}records")
        
        # Perform consistency check
        result = checker.check_daily_basic_consistency(
            primary_data, secondary_data, "Tushare", "AKShare"
        )
        
        print(f"\n📈 Consistency check results:")
        print(f"   data consistency: {result.is_consistent}")
        print(f"   confidence score: {result.confidence_score:.3f}")
        print(f"   Recommended action: {result.recommended_action}")
        
        print(f"\n📊 Detailed differences:")
        for metric, diff in result.differences.items():
            if isinstance(diff, dict):
                print(f"   {metric}:")
                print(f"     Primary data source average: {diff.get('primary_value', 'N/A')}")
                print(f"     average of secondary data sources: {diff.get('secondary_value', 'N/A')}")
                if diff.get('difference_pct') is not None:
                    print(f"     Difference percentage: {diff['difference_pct']:.2%}")
                print(f"     Is it significant?: {diff.get('is_significant', False)}")
        
        # Test conflict resolution
        final_data, strategy = checker.resolve_data_conflicts(
            primary_data, secondary_data, result
        )
        
        print(f"\n🔧 conflict resolution:")
        print(f"   Strategy: {strategy}")
        print(f"   The final number of data items: {len(final_data)}")
        
        print(f"\n✅ Simulated data test completed")
        
    except Exception as e:
        print(f"❌ Simulated data test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_data_consistency_checker()
    test_mock_data_consistency()
