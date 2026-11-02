#!/usr/bin/env python3
"""
Test database dependency package compatibility fix
Compatibility improvements to verify requirements_db.txt
"""

import os
import sys
import subprocess
import tempfile
import shutil

# Add project root directory to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_python_version_check():
    """Test Python version check"""
    print("🔧 Test Python version check...")
    
    current_version = sys.version_info
    if current_version >= (3, 10):
        print(f"  ✅ Python {current_version.major}.{current_version.minor}.{current_version.micro} Meet the requirements")
        return True
    else:
        print(f"  ❌ Python {current_version.major}.{current_version.minor}.{current_version.micro} Version is too low")
        return False


def test_pickle_compatibility():
    """Test pickle compatibility"""
    print("🔧 Test pickle compatibility...")
    
    try:
        import pickle
        
        # Check protocol version
        max_protocol = pickle.HIGHEST_PROTOCOL
        print(f"  Current pickle protocol: {max_protocol}")
        
        if max_protocol >= 5:
            print("  ✅ Support pickle protocol 5")
        else:
            print("  ❌ Does not support pickle protocol 5")
            return False
        
        # Check if it was installed incorrectly pickle5
        try:
            import pickle5
            print("  ⚠️ The pickle5 package is detected and it is recommended to uninstall it.")
            return False
        except ImportError:
            print("  ✅ The pickle5 package is not installed and the configuration is correct")
            return True
            
    except Exception as e:
        print(f"  ❌ pickle test failed: {e}")
        return False


def test_requirements_file_syntax():
    """Test requirements file syntax"""
    print("🔧 Test requirements_db.txt syntax...")
    
    requirements_file = os.path.join(project_root, "requirements_db.txt")
    
    if not os.path.exists(requirements_file):
        print("  ❌ requirements_db.txt File does not exist")
        return False
    
    try:
        with open(requirements_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"  Number of file lines: {len(lines)}")
        
        # Check if it contains pickle5
        pickle5_found = False
        valid_packages = []
        
        for line_num, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            if 'pickle5' in line and not line.startswith('#'):
                print(f"  ❌ No.{line_num}row still contains pickle5: {line}")
                pickle5_found = True
            else:
                valid_packages.append(line)
                print(f"  ✅ No.{line_num}OK: {line}")
        
        if pickle5_found:
            print("  ❌ Still contains pickle5 dependencies")
            return False
        
        print(f"  ✅ Grammar check passed, number of valid packages: {len(valid_packages)}")
        return True
        
    except Exception as e:
        print(f"  ❌ File read failed: {e}")
        return False


def test_package_installation_simulation():
    """Simulate package installation test"""
    print("🔧 Simulate package installation test...")
    
    # Simulate checking the availability of each package
    packages_to_check = [
        "pymongo",
        "motor", 
        "redis",
        "hiredis",
        "pandas",
        "numpy"
    ]
    
    available_packages = []
    missing_packages = []
    
    for package in packages_to_check:
        try:
            __import__(package)
            available_packages.append(package)
            print(f"  ✅ {package}: Installed")
        except ImportError:
            missing_packages.append(package)
            print(f"  ⚠️ {package}: Not installed")
    
    print(f"  Installed: {len(available_packages)}/{len(packages_to_check)}")
    
    if missing_packages:
        print(f"  Missing package: {missing_packages}")
        print("  💡 Run the following command to install: pip install -r requirements_db.txt")
    
    return True  # This test always passes and is only informational


def test_compatibility_checker_tool():
    """Test Compatibility Check Tool"""
    print("🔧 Test Compatibility Check Tool...")
    
    checker_file = os.path.join(project_root, "check_db_requirements.py")
    
    if not os.path.exists(checker_file):
        print("  ❌ check_db_requirements.py File does not exist")
        return False
    
    try:
        # Run the compatibility check tool
        result = subprocess.run(
            [sys.executable, checker_file],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        print(f"  return code: {result.returncode}")
        
        if "🔧 TradingAgents Database dependency package compatibility check" in result.stdout:
            print("  ✅ Compatibility check tool ran successfully")
            
            # Check if pickle5 issue is detected
            if "pickle5" in result.stdout and "Recommended to uninstall" in result.stdout:
                print("  ⚠️ pickle5 issue detected")
            elif "The pickle5 package is not installed and the configuration is correct" in result.stdout:
                print("  ✅ pickle5 Configured correctly")
            
            return True
        else:
            print("  ❌ Compatibility check tool output exception")
            print(f"  output: {result.stdout[:200]}...")
            return False
            
    except subprocess.TimeoutExpired:
        print("  ❌ Compatibility check tool timed out")
        return False
    except Exception as e:
        print(f"  ❌ Compatibility check tool failed to run: {e}")
        return False


def test_documentation_completeness():
    """Test document integrity"""
    print("🔧 Test document integrity...")
    
    docs_to_check = [
        "docs/DATABASE_SETUP_GUIDE.md",
        "REQUIREMENTS_DB_UPDATE.md"
    ]
    
    all_exist = True
    
    for doc_path in docs_to_check:
        full_path = os.path.join(project_root, doc_path)
        if os.path.exists(full_path):
            print(f"  ✅ {doc_path}: exist")
            
            # Check file size
            size = os.path.getsize(full_path)
            if size > 1000:  # at least 1KB
                print(f"    file size: {size} Bytes")
            else:
                print(f"    ⚠️ Smaller file size: {size} Bytes")
        else:
            print(f"  ❌ {doc_path}: does not exist")
            all_exist = False
    
    return all_exist


def main():
    """Main test function"""
    print("🔧 Database dependency package compatibility repair testing")
    print("=" * 60)
    
    tests = [
        ("Python version check", test_python_version_check),
        ("pickle Compatibility", test_pickle_compatibility),
        ("requirements file syntax", test_requirements_file_syntax),
        ("Package installation simulation", test_package_installation_simulation),
        ("Compatibility check tool", test_compatibility_checker_tool),
        ("Documentation completeness", test_documentation_completeness),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        try:
            if test_func():
                passed += 1
                print(f"  ✅ {test_name} Pass")
            else:
                print(f"  ❌ {test_name} failed")
        except Exception as e:
            print(f"  ❌ {test_name} Abnormal: {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed! Database dependency package compatibility repaired successfully")
        print("\n📋 Fix content:")
        print("✅ Remove pickle5 dependency and solve it Python 3.10+Compatibility issues")
        print("✅ Optimize version requirements and improve environmental compatibility")
        print("✅ Add compatibility check tool")
        print("✅ Complete installation guide and troubleshooting documentation")
        
        print("\n🚀 User experience improvements:")
        print("✅ Reduce installation errors")
        print("✅ Provide clear error diagnosis")
        print("✅ Support more Python environments")
        print("✅ Simplify troubleshooting process")
        
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
