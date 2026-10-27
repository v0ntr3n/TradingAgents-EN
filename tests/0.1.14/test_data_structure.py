#!/usr/bin/env python3
"""
Test data structure script
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'web'))

def test_data_structure():
    """Test analysis result data structure"""
    try:
        from web.components.analysis_results import load_analysis_results
        
        print("🔍 Test analysis result data structure...")
        
        # Load analysis results
        results = load_analysis_results(limit=5)
        
        print(f"📊 found {len(results)} analysis results")
        
        if results:
            result = results[0]
            print(f"\n📋 The data structure of the first result:")
            print(f"   analysis_id: {result.get('analysis_id', 'missing')}")
            print(f"   source: {result.get('source', 'missing')}")
            print(f"   stock_symbol: {result.get('stock_symbol', 'missing')}")
            print(f"   reports Field exists: {'reports' in result}")
            
            if 'reports' in result:
                reports = result['reports']
                print(f"   reports content: {list(reports.keys())}")
                
                # Display first 100 characters of first report
                if reports:
                    first_report_key = list(reports.keys())[0]
                    first_report_content = reports[first_report_key]
                    print(f"   {first_report_key} Content preview:")
                    print(f"   {first_report_content[:200]}...")
            else:
                print("   ❌ reports Field does not exist")
                print(f"   Available fields: {list(result.keys())}")
        
        return results
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    test_data_structure()
