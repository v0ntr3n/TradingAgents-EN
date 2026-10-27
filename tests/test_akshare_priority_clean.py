#!/usr/bin/env python3
"""
Clean test AKShare data source priority fix
Force module reload to avoid caching issues
"""

import os
import sys
import importlib

# Add project root directory to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

def clean_import_test():
    """Clean import tests"""
    print("🧹 Clean import tests")
    print("=" * 60)
    
    try:
        # Clean possible module cache
        modules_to_clean = [
            'tradingagents.dataflows.data_source_manager',
            'tradingagents.dataflows',
            'tradingagents'
        ]
        
        for module_name in modules_to_clean:
            if module_name in sys.modules:
                print(f"🗑️ Clean module cache: {module_name}")
                del sys.modules[module_name]
        
        # Reimport
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        # Create data source manager
        manager = DataSourceManager()
        
        print(f"📊 Default data source: {manager.default_source.value}")
        print(f"📊 Current data source: {manager.current_source.value}")
        print(f"📊 Available data sources: {[s.value for s in manager.available_sources]}")
        
        # Verify that the default data source is AKShare
        if manager.default_source == ChinaDataSource.AKSHARE:
            print("✅ The default data source is correctly set to AKShare")
            return True
        else:
            print(f"❌ Default data source error: expected akshare, actual{manager.default_source.value}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_env_variable_directly():
    """Test environment variables directly"""
    print("\n🔧 Test environment variables directly")
    print("=" * 60)
    
    try:
        # Check environment variables
        env_value = os.getenv('DEFAULT_CHINA_DATA_SOURCE')
        print(f"📊 environment variables DEFAULT_CHINA_DATA_SOURCE: {env_value}")
        
        # Check .env file
        env_file_path = os.path.join(project_root, '.env')
        if os.path.exists(env_file_path):
            print(f"📄 .env File exists: {env_file_path}")
            with open(env_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'DEFAULT_CHINA_DATA_SOURCE' in content:
                    for line in content.split('\n'):
                        if 'DEFAULT_CHINA_DATA_SOURCE' in line and not line.strip().startswith('#'):
                            print(f"📊 .env settings in file: {line.strip()}")
                            break
        else:
            print("📄 .env File does not exist")
        
        # Manually load .env files
        try:
            from dotenv import load_dotenv
            load_dotenv()
            env_value_after_load = os.getenv('DEFAULT_CHINA_DATA_SOURCE')
            print(f"📊 Environment variables after loading .env: {env_value_after_load}")
        except ImportError:
            print("⚠️ python-dotenv Not installed, cannot automatically load .env file")
        
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_manual_env_setting():
    """Manually set environment variables for testing"""
    print("\n🔧 Manually set environment variables for testing")
    print("=" * 60)
    
    try:
        # Manually set environment variables
        os.environ['DEFAULT_CHINA_DATA_SOURCE'] = 'akshare'
        print(f"📊 Manually set environment variables: DEFAULT_CHINA_DATA_SOURCE=akshare")
        
        # Clean module cache
        modules_to_clean = [
            'tradingagents.dataflows.data_source_manager',
        ]
        
        for module_name in modules_to_clean:
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        # Reimport
        from tradingagents.dataflows.data_source_manager import DataSourceManager, ChinaDataSource
        
        manager = DataSourceManager()
        
        print(f"📊 Default data source: {manager.default_source.value}")
        print(f"📊 Current data source: {manager.current_source.value}")
        
        if manager.default_source == ChinaDataSource.AKSHARE:
            print("✅ After manually setting the environment variables, the default data source is correctly AKShare")
            return True
        else:
            print(f"❌ After manually setting environment variables, the default data source is still wrong: {manager.default_source.value}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_fallback_order():
    """Test alternative data source sequence"""
    print("\n🔧 Test alternative data source sequence")
    print("=" * 60)
    
    try:
        # Make sure environment variables are set
        os.environ['DEFAULT_CHINA_DATA_SOURCE'] = 'akshare'
        
        # Clean and re-import
        if 'tradingagents.dataflows.data_source_manager' in sys.modules:
            del sys.modules['tradingagents.dataflows.data_source_manager']
        
        from tradingagents.dataflows.data_source_manager import DataSourceManager
        
        manager = DataSourceManager()
        
        # Check the source code for fallback_order
        import inspect
        source_code = inspect.getsource(manager._try_fallback_sources)
        
        print("📊 Check alternate data source order...")
        
        # Find fallback_order definition
        lines = source_code.split('\n')
        in_fallback_order = False
        fallback_sources = []
        
        for line in lines:
            if 'fallback_order = [' in line:
                in_fallback_order = True
                continue
            elif in_fallback_order:
                if ']' in line:
                    break
                if 'ChinaDataSource.' in line:
                    source_name = line.strip().replace('ChinaDataSource.', '').replace(',', '')
                    fallback_sources.append(source_name)
        
        print(f"📊 Alternate data source order: {fallback_sources}")
        
        if fallback_sources and fallback_sources[0] == 'AKSHARE':
            print("✅ Alternate data sources are in the correct order: AKShare ranked first")
            return True
        else:
            print(f"❌ Alternate data sources in wrong order: Expect AKSHARE first, actual order: {fallback_sources}")
            return False
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("🧪 AKShare Data source priority repair verification (Cleaned version)")
    print("=" * 80)
    
    tests = [
        ("Environment variable check", test_env_variable_directly),
        ("Manual environment variable settings", test_manual_env_setting),
        ("Clean import tests", clean_import_test),
        ("Alternate data source order", test_fallback_order),
    ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n🔍 Execute tests: {test_name}")
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ test{test_name}Abnormal: {e}")
            results.append((test_name, False))
    
    # Summary results
    print("\n" + "=" * 80)
    print("📊 Summary of test results:")
    
    passed = 0
    total = len(results)
    
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"  {test_name}: {status}")
        if result:
            passed += 1
    
    print(f"\n🎯 Overall results: {passed}/{total} Test passed")
    
    if passed == total:
        print("🎉 All tests passed! AKShare data source priority repaired successfully!")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
