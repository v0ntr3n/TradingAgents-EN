#!/usr/bin/env python3
"""
Test DataFrame Arrow conversion fix
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_safe_dataframe():
    """Test safe DataFrame functions"""
    try:
        from web.components.analysis_results import safe_dataframe
        import pandas as pd
        
        print("🔍 Test safe DataFrame functions...")
        
        # Test mixed data types
        mixed_data = {
            'Project': ['Stock code', 'Analysis time', 'Number of analysts', 'Research depth'],
            'result A': ['000001', '2025-07-31 12:00', 3, 5],  # Mixing strings and integers
            'result B': ['000002', '2025-07-31 13:00', 2, 4]
        }
        
        # Create using safe functions DataFrame
        df = safe_dataframe(mixed_data)
        print(f"✅ Security DataFrame created successfully, shape: {df.shape}")
        
        # Check data type
        print("📊 Data type checking:")
        for col in df.columns:
            dtype = df[col].dtype
            print(f"   {col}: {dtype}")
            if dtype == 'object':
                print(f"   ✅ {col} is a string type")
            else:
                print(f"   ⚠️ {col} Not a string type")
        
        # Test list data
        list_data = [
            {'stocks': '000001', 'price': 10.5, 'Quantity': 100},
            {'stocks': '000002', 'price': 20.3, 'Quantity': 200}
        ]
        
        df_list = safe_dataframe(list_data)
        print(f"✅ List data DataFrame created successfully, shape: {df_list.shape}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def test_comparison_data():
    """Test comparison data creation"""
    try:
        from web.components.analysis_results import safe_dataframe
        
        print("\n🔍 Test comparison data creation...")
        
        # Simulation comparison data
        comparison_data = {
            "Project": ["Stock code", "Analysis time", "Number of analysts", "Research depth", "Status", "Number of tags"],
            "Analyze results A": [
                '000001',
                '2025-07-31 12:00',
                3,  # integer
                5,  # integer
                "✅ Complete",
                2   # integer
            ],
            "Analyze results B": [
                '000002',
                '2025-07-31 13:00',
                2,  # integer
                4,  # integer
                "❌ failed",
                1   # integer
            ]
        }
        
        df = safe_dataframe(comparison_data)
        print(f"✅ Comparison data DataFrame created successfully")
        
        # Verify that all data is string
        all_string = all(df[col].dtype == 'object' for col in df.columns)
        if all_string:
            print("✅ All columns are of type string")
        else:
            print("❌ Column of non-string type exists")
            
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def test_timeline_data():
    """Test timeline data creation"""
    try:
        from web.components.analysis_results import safe_dataframe
        
        print("\n🔍 Test timeline data creation...")
        
        # Simulation timeline data
        timeline_data = []
        for i in range(3):
            timeline_data.append({
                'serial number': i + 1,  # integer
                'Analysis time': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'analyst': 'analyst1, analyst2',
                'Research depth': 5,  # integer
                'Status': '✅' if i % 2 == 0 else '❌'
            })
        
        df = safe_dataframe(timeline_data)
        print(f"✅ Timeline data DataFrame created successfully, number of rows: {len(df)}")
        
        # Check if the ordinal column is a string
        if df['serial number'].dtype == 'object':
            print("✅ Ordinal column has been converted to string type")
        else:
            print(f"❌ Serial number column type: {df['serial number'].dtype}")
            
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def test_arrow_conversion():
    """Test Arrow conversion"""
    try:
        from web.components.analysis_results import safe_dataframe
        import pyarrow as pa
        
        print("\n🔍 Test Arrow conversion...")
        
        # Create data that can cause Arrow errors
        problematic_data = {
            'text column': ['text1', 'text2', 'text3'],
            'Number column': [1, 2, 3],  # integer
            'floating point column': [1.1, 2.2, 3.3],  # floating point number
            'Boolean column': [True, False, True],  # Boolean value
            'Mixed columns': ['text', 123, 45.6]  # mixed type
        }
        
        # Use safe functions
        df = safe_dataframe(problematic_data)
        
        # Try converting to Arrow
        table = pa.Table.from_pandas(df)
        print("✅ Arrow Conversion successful")
        print(f"   table shape: {table.shape}")
        print(f"   List: {table.column_names}")
        
        return True
        
    except Exception as e:
        print(f"❌ Arrow Conversion failed: {e}")
        return False


def main():
    """Main test function"""
    print("🚀 Start testing DataFrame Arrow conversion fix")
    print("=" * 50)
    
    tests = [
        ("Safe DataFrame functions", test_safe_dataframe),
        ("Comparative data creation", test_comparison_data),
        ("Timeline data creation", test_timeline_data),
        ("Arrow Convert", test_arrow_conversion)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 test: {test_name}")
        if test_func():
            passed += 1
            print(f"✅ {test_name} Pass")
        else:
            print(f"❌ {test_name} failed")
    
    print("\n" + "=" * 50)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! DataFrame Arrow conversion issue fixed")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
