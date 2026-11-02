"""
Debug web interface display"True"question
"""

import sys
import os
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_form_data_structure():
    """Test form data structure"""
    print("🧪 Test form data structure...")
    
    try:
        # Mock form data
        form_data_submitted = {
            'submitted': True,
            'stock_symbol': '0700.HK',
            'market_type': 'Hong Kong stocks',
            'analysis_date': '2025-07-14',
            'analysts': ['market', 'fundamentals'],
            'research_depth': 3,
            'include_sentiment': True,
            'include_risk_assessment': True,
            'custom_prompt': ''
        }
        
        form_data_not_submitted = {
            'submitted': False
        }
        
        print("  Form data on submission:")
        for key, value in form_data_submitted.items():
            print(f"    {key}: {value} ({type(value).__name__})")
        
        print("\n  Form data when not submitted:")
        for key, value in form_data_not_submitted.items():
            print(f"    {key}: {value} ({type(value).__name__})")
        
        # Check condition judgment
        if form_data_submitted.get('submitted', False):
            print("\n  ✅ The submission conditions are correct")
        else:
            print("\n  ❌ Submit condition judgment error")
        
        if form_data_not_submitted.get('submitted', False):
            print("  ❌ Uncommitted condition judgment error")
        else:
            print("  ✅ The unsubmitted condition is judged correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Form data structure test failed: {e}")
        return False

def test_validation_function():
    """Test verification function"""
    print("\n🧪 Test verification function...")
    
    try:
        from web.utils.analysis_runner import validate_analysis_params
        
        # Test Hong Kong stock verification
        errors = validate_analysis_params(
            stock_symbol="0700.HK",
            analysis_date="2025-07-14",
            analysts=["market", "fundamentals"],
            research_depth=3,
            market_type="Hong Kong stocks"
        )
        
        print(f"  Hong Kong stock verification results: {errors}")
        
        if not errors:
            print("  ✅ Hong Kong stock verification passed")
        else:
            print(f"  ❌ Hong Kong stock verification failed: {errors}")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Validation function test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_analysis_runner_import():
    """Test analysis runner import"""
    print("\n🧪 Test analysis runner import...")
    
    try:
        from web.utils.analysis_runner import run_stock_analysis, validate_analysis_params, format_analysis_results
        print("  ✅ Analysis runner imported successfully")
        
        # Test function signature
        import inspect
        
        sig = inspect.signature(run_stock_analysis)
        print(f"  run_stock_analysis parameters: {list(sig.parameters.keys())}")
        
        sig = inspect.signature(validate_analysis_params)
        print(f"  validate_analysis_params parameters: {list(sig.parameters.keys())}")
        
        return True
        
    except Exception as e:
        print(f"❌ Analysis runner import failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_streamlit_components():
    """Test the Streamlit component"""
    print("\n🧪 Test the Streamlit component...")
    
    try:
        # Test component import
        from web.components.analysis_form import render_analysis_form
        from web.components.results_display import render_results
        
        print("  ✅ Streamlit Component imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Streamlit Component test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_potential_output_sources():
    """Check possible output sources"""
    print("\n🧪 Check possible output sources...")
    
    # Check possible output"True"place
    potential_sources = [
        "Direct output of form submission status",
        "Convert boolean to string",
        "Debugging statement remains",
        "Output from exception handling",
        "Streamlit Unexpected output from component"
    ]
    
    for source in potential_sources:
        print(f"  🔍 Check: {source}")
    
    print("\n  💡 Recommended to check:")
    print("    1. Search code for st.write(True) or similar statement")
    print("    2. Check if there is print(True) statement")
    print("    3. Check to see if any Boolean values are being displayed unexpectedly")
    print("    4. Check the return value handling of form components")
    
    return True

def main():
    """Run all debug tests"""
    print("🐛 Start debugging the web interface'True'display problem")
    print("=" * 50)
    
    tests = [
        test_form_data_structure,
        test_validation_function,
        test_analysis_runner_import,
        test_streamlit_components,
        check_potential_output_sources
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Abnormal: {e}")
    
    print("\n" + "=" * 50)
    print(f"🐛 Debugging test completed: {passed}/{total} Pass")
    
    if passed == total:
        print("✅ All tests passed, the problem may be in the Streamlit runtime environment")
    else:
        print("⚠️ Problem found, please check failed test items")
    
    print("\n🔧 Solution suggestions:")
    print("1. Restart the Streamlit application")
    print("2. Clear browser cache")
    print("3. Check for residual debug output")
    print("4. Confirm that all components are imported correctly")

if __name__ == "__main__":
    main()
