#!/usr/bin/env python3
"""
VSCode Configuration verification test
Verify that the Python virtual environment and project configuration are correct
"""

import os
import sys
import json
import subprocess
from pathlib import Path


def test_python_environment():
    """Test Python environment configuration"""
    print("🐍 Python Environmental verification")
    print("=" * 50)
    
    # Check Python version
    print(f"Python version: {sys.version}")
    print(f"Python path: {sys.executable}")
    
    # Check virtual environment
    venv_path = os.environ.get('VIRTUAL_ENV')
    if venv_path:
        print(f"✅ virtual environment: {venv_path}")
    else:
        print("⚠️ virtual environment: Not activated")
    
    # Check working directory
    print(f"working directory: {os.getcwd()}")
    
    # Check if it is in the project root directory
    if os.path.exists('tradingagents') and os.path.exists('.env'):
        print("✅ In the project root directory")
    else:
        print("❌ Not in the project root directory")
    
    return True


def test_vscode_settings():
    """Test VSCode settings file"""
    print("\n🔧 VSCode Set up verification")
    print("=" * 50)
    
    settings_path = Path('.vscode/settings.json')
    
    if not settings_path.exists():
        print("❌ .vscode/settings.json does not exist")
        return False
    
    try:
        with open(settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        
        print("✅ settings.json Correct format")
        
        # Check key configuration
        key_settings = {
            'python.defaultInterpreterPath': './env/Scripts/python.exe',
            'python.terminal.activateEnvironment': True,
            'python.testing.pytestEnabled': True,
        }
        
        for key, expected in key_settings.items():
            if key in settings:
                actual = settings[key]
                if actual == expected:
                    print(f"✅ {key}: {actual}")
                else:
                    print(f"⚠️ {key}: {actual} (Expectation: {expected})")
            else:
                print(f"❌ Missing configuration: {key}")
        
        return True
        
    except json.JSONDecodeError as e:
        print(f"❌ settings.json Format error: {e}")
        return False
    except Exception as e:
        print(f"❌ Failed to read settings.json: {e}")
        return False


def test_virtual_env_path():
    """Test virtual environment path"""
    print("\n📁 Virtual environment path verification")
    print("=" * 50)
    
    # Check the virtual environment directory
    env_dir = Path('env')
    if not env_dir.exists():
        print("❌ env Directory does not exist")
        return False
    
    print("✅ env Directory exists")
    
    # Check Python executable
    python_exe = env_dir / 'Scripts' / 'python.exe'
    if python_exe.exists():
        print(f"✅ Python executable file: {python_exe}")
    else:
        print(f"❌ Python Executable file does not exist: {python_exe}")
        return False
    
    # Check pip
    pip_exe = env_dir / 'Scripts' / 'pip.exe'
    if pip_exe.exists():
        print(f"✅ pip executable file: {pip_exe}")
    else:
        print(f"❌ pip Executable file does not exist: {pip_exe}")
    
    return True


def test_package_imports():
    """Test key package import"""
    print("\n📦 Key package import verification")
    print("=" * 50)
    
    packages = [
        ('langchain', 'LangChain'),
        ('langchain_openai', 'LangChain OpenAI'),
        ('pandas', 'Pandas'),
        ('numpy', 'NumPy'),
        ('tushare', 'Tushare'),
        ('streamlit', 'Streamlit'),
        ('tradingagents', 'TradingAgents')
    ]
    
    success_count = 0
    for package, name in packages:
        try:
            module = __import__(package)
            version = getattr(module, '__version__', 'unknown')
            print(f"✅ {name}: v{version}")
            success_count += 1
        except ImportError:
            print(f"❌ {name}: Not installed")
        except Exception as e:
            print(f"⚠️ {name}: import error - {e}")
    
    print(f"\n📊 Package import results: {success_count}/{len(packages)} success")
    return success_count >= len(packages) * 0.8  # 80%success rate


def test_project_structure():
    """Test project structure"""
    print("\n📂 Project structure verification")
    print("=" * 50)
    
    required_dirs = [
        'tradingagents',
        'tests',
        'cli',
        'web',
        '.vscode'
    ]
    
    required_files = [
        '.env',
        'requirements.txt',
        'README.md',
        '.gitignore'
    ]
    
    # Check directory
    for dir_name in required_dirs:
        if os.path.exists(dir_name):
            print(f"✅ Directory: {dir_name}")
        else:
            print(f"❌ Directory: {dir_name}")
    
    # Check files
    for file_name in required_files:
        if os.path.exists(file_name):
            print(f"✅ File: {file_name}")
        else:
            print(f"❌ File: {file_name}")
    
    return True


def test_environment_variables():
    """Test environment variables"""
    print("\n🔑 Environment variable verification")
    print("=" * 50)
    
    # Read .env file
    env_file = Path('.env')
    if not env_file.exists():
        print("❌ .env File does not exist")
        return False
    
    print("✅ .env File exists")
    
    # Check key environment variables
    key_vars = [
        'DASHSCOPE_API_KEY',
        'TUSHARE_TOKEN',
        'OPENAI_API_KEY',
        'FINNHUB_API_KEY'
    ]
    
    for var in key_vars:
        value = os.getenv(var)
        if value:
            print(f"✅ {var}: {'*' * 10}{value[-4:] if len(value) > 4 else '****'}")
        else:
            print(f"⚠️ {var}: not set")
    
    return True


def test_simple_functionality():
    """Test basic functionality"""
    print("\n⚡ Basic functional verification")
    print("=" * 50)
    
    try:
        # Test TradingAgents import
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        print("✅ TradingAgents LLM Adapter imported successfully")
        
        # Test data flow import
        from tradingagents.dataflows import get_china_stock_data_unified
        print("✅ TradingAgents Data flow imported successfully")
        
        # Test graphic import
        from tradingagents.graph.trading_graph import TradingAgentsGraph
        print("✅ TradingAgents Graphics imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Functional test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔬 VSCode Configuration verification test")
    print("=" * 70)
    print("💡 Verify target:")
    print("   - Python Virtual environment configuration")
    print("   - VSCode settings file")
    print("   - Project structural integrity")
    print("   - Key package import")
    print("   - Environment variable configuration")
    print("=" * 70)
    
    # Run all tests
    tests = [
        ("Python environment", test_python_environment),
        ("VSCode settings", test_vscode_settings),
        ("virtual environment path", test_virtual_env_path),
        ("Package import", test_package_imports),
        ("Project structure", test_project_structure),
        ("environment variables", test_environment_variables),
        ("Basic functions", test_simple_functionality)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name}Test exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n📋 VSCode Configuration verification summary")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 VSCode The configuration is completely correct!")
        print("\n💡 Now you can:")
        print("   ✅ Develop and debug normally in VSCode")
        print("   ✅ Run Python code using the integrated terminal")
        print("   ✅ Run tests and format code")
        print("   ✅ Use smart code completion and error checking")
    elif passed >= total * 0.8:
        print("\n✅ VSCode The configuration is basically correct!")
        print("⚠️ Some functions may need to be adjusted")
    else:
        print("\n⚠️ VSCode Configuration needs fixing")
        print("Please check the failed project and reconfigure")
    
    print("\n🎯 Usage suggestions:")
    print("   1. Make sure the correct Python interpreter is selected in VSCode")
    print("   2. Restart VSCode to apply the new configuration")
    print("   3. Use Ctrl+Shift+P -> 'Python: Select Interpreter'")
    print("   4. Verify that the virtual environment is activated in the integrated terminal")


if __name__ == "__main__":
    main()
