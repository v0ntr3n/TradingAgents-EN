#!/usr/bin/env python3
"""
Test enhanced analysis history capabilities
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_load_analysis_results():
    """Test loading analysis results function"""
    try:
        from web.components.analysis_results import load_analysis_results
        
        print("🔍 Test loading analysis results...")
        
        # Test basic loading
        results = load_analysis_results(limit=10)
        print(f"✅ successfully loaded {len(results)} analysis results")
        
        if results:
            # Check result structure
            first_result = results[0]
            required_fields = ['analysis_id', 'timestamp', 'stock_symbol', 'status']
            
            for field in required_fields:
                if field in first_result:
                    print(f"✅ Field '{field}' exist")
                else:
                    print(f"❌ Field '{field}' Missing")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def test_comparison_functions():
    """Test comparison function"""
    try:
        from web.components.analysis_results import (
            calculate_text_similarity,
            get_report_content
        )
        
        print("🔍 Test comparison function...")
        
        # Test text similarity calculation
        text1 = "This is a test text"
        text2 = "This is another test text"
        similarity = calculate_text_similarity(text1, text2)
        print(f"✅ Text similarity calculation: {similarity:.2f}")
        
        # Obtain test report content
        mock_result = {
            'source': 'file_system',
            'reports': {
                'final_trade_decision': 'Buy recommendation'
            }
        }
        
        content = get_report_content(mock_result, 'final_trade_decision')
        print(f"✅ Obtain report content: {content}")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def test_chart_functions():
    """Test chart functionality"""
    try:
        import pandas as pd
        from web.components.analysis_results import (
            render_comprehensive_dashboard,
            render_time_distribution_charts
        )
        
        print("🔍 Test chart functionality...")
        
        # Create simulated data
        mock_data = []
        for i in range(10):
            mock_data.append({
                'timestamp': datetime.now() - timedelta(days=i),
                'stock_symbol': f'00000{i % 3}',
                'status': 'completed' if i % 2 == 0 else 'failed',
                'analysts_count': 3,
                'research_depth': 5,
                'tags_count': 2,
                'summary_length': 100 + i * 10,
                'date': (datetime.now() - timedelta(days=i)).date(),
                'hour': 10 + i % 12,
                'weekday': i % 7
            })
        
        df = pd.DataFrame(mock_data)
        print(f"✅ Create simulated data: {len(df)} records")
        
        # Note: This is just to test whether the function can be imported. Actual rendering requires the Streamlit environment.
        print("✅ Chart function imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False


def create_test_data():
    """Create test data"""
    try:
        print("🔍 Create test data...")
        
        # Make sure the test data directory exists
        test_data_dir = project_root / "data" / "analysis_results" / "detailed" / "TEST001"
        test_date_dir = test_data_dir / "2025-07-31" / "reports"
        test_date_dir.mkdir(parents=True, exist_ok=True)
        
        # Create test report
        test_reports = {
            'final_trade_decision.md': '# Test trading decisions\n\n Recommended to buy',
            'fundamentals_report.md': '# Test fundamental analysis\n\n The company s fundamentals are good',
            'market_report.md': '# Test technical analysis\n\n Technical indicators point to an uptrend'
        }
        
        for filename, content in test_reports.items():
            report_file = test_date_dir / filename
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(content)
        
        print(f"✅ Test data created successfully: {test_date_dir}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to create test data: {e}")
        return False


def main():
    """Main test function"""
    print("🚀 Start testing enhanced analysis history capabilities")
    print("=" * 50)
    
    tests = [
        ("Create test data", create_test_data),
        ("Load analysis results", test_load_analysis_results),
        ("Compare function", test_comparison_functions),
        ("Chart function", test_chart_functions)
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
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️ Some tests failed, please check the code")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
