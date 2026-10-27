#!/usr/bin/env python3
"""
Debugging import issues
"""

import sys
from pathlib import Path

# Add project root directory to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_google_news_import():
    """Test Google News tool import"""
    print("🧪 Test Google News tool import")
    print("=" * 50)
    
    try:
        # Try different import methods
        print("1. Try importing the googlenews_utils module...")
        from tradingagents.dataflows import googlenews_utils
        print("✅ googlenews_utils Module imported successfully")
        
        # Check the functions in the module
        print("2. Check the functions in the module...")
        functions = [attr for attr in dir(googlenews_utils) if not attr.startswith('_')]
        print(f"   Available functions: {functions}")
        
        # Try to import a specific function
        print("3. Try to import a specific function...")
        if hasattr(googlenews_utils, 'get_google_news'):
            print("✅ get_google_news function exists")
        else:
            print("❌ get_google_news function does not exist")
            
        if hasattr(googlenews_utils, 'getNewsData'):
            print("✅ getNewsData function exists")
        else:
            print("❌ getNewsData function does not exist")
            
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Other errors: {e}")
        return False

def test_reddit_import():
    """Test Reddit tool import"""
    print("\n🧪 Test Reddit tool import")
    print("=" * 50)
    
    try:
        # Try different import methods
        print("1. Try importing the reddit_utils module...")
        from tradingagents.dataflows import reddit_utils
        print("✅ reddit_utils Module imported successfully")
        
        # Check the functions in the module
        print("2. Check the functions in the module...")
        functions = [attr for attr in dir(reddit_utils) if not attr.startswith('_')]
        print(f"   Available functions: {functions}")
        
        # Try to import a specific function
        print("3. Try to import a specific function...")
        if hasattr(reddit_utils, 'get_reddit_sentiment'):
            print("✅ get_reddit_sentiment function exists")
        else:
            print("❌ get_reddit_sentiment function does not exist")
            
        # Check other possible function names
        possible_functions = ['get_reddit_data', 'fetch_reddit_posts', 'analyze_reddit_sentiment']
        for func_name in possible_functions:
            if hasattr(reddit_utils, func_name):
                print(f"✅ {func_name}function exists")
            
        return True
        
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Other errors: {e}")
        return False

def check_dependencies():
    """Check dependent libraries"""
    print("\n🧪 Check dependent libraries")
    print("=" * 50)
    
    dependencies = {
        'requests': 'HTTP request library',
        'beautifulsoup4': 'HTML Parsing library',
        'praw': 'Reddit API Library',
        'tenacity': 'Retry mechanism library'
    }
    
    for package, description in dependencies.items():
        try:
            if package == 'beautifulsoup4':
                import bs4
                print(f"✅ {description}: Installed")
            else:
                __import__(package)
                print(f"✅ {description}: Installed")
        except ImportError:
            print(f"❌ {description}: Not installed (pip install {package})")

def check_actual_file_contents():
    """Check actual file content"""
    print("\n🧪 Check actual file content")
    print("=" * 50)
    
    # Check Google News files
    try:
        google_file = Path("tradingagents/dataflows/googlenews_utils.py")
        if google_file.exists():
            print(f"✅ Google News File exists: {google_file}")
            with open(google_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'def ' in content:
                    # Extract function definition
                    import re
                    functions = re.findall(r'def (\w+)\(', content)
                    print(f"   function in file: {functions}")
                else:
                    print("   There is no function definition in the file")
        else:
            print(f"❌ Google News File does not exist: {google_file}")
    except Exception as e:
        print(f"❌ Checking Google News files failed: {e}")
    
    # Check Reddit file
    try:
        reddit_file = Path("tradingagents/dataflows/reddit_utils.py")
        if reddit_file.exists():
            print(f"✅ Reddit File exists: {reddit_file}")
            with open(reddit_file, 'r', encoding='utf-8') as f:
                content = f.read()
                if 'def ' in content:
                    # Extract function definition
                    import re
                    functions = re.findall(r'def (\w+)\(', content)
                    print(f"   function in file: {functions}")
                else:
                    print("   There is no function definition in the file")
        else:
            print(f"❌ Reddit File does not exist: {reddit_file}")
    except Exception as e:
        print(f"❌ Checking Reddit file failed: {e}")

def main():
    """main function"""
    print("🔍 Diagnostic tool import issues")
    print("=" * 60)
    
    # Check dependent libraries
    check_dependencies()
    
    # Check file contents
    check_actual_file_contents()
    
    # Test import
    google_success = test_google_news_import()
    reddit_success = test_reddit_import()
    
    print(f"\n📊 Diagnosis results:")
    print(f"  Google News Tools: {'✅ Available' if google_success else '❌ Not available'}")
    print(f"  Reddit Tools: {'✅ Available' if reddit_success else '❌ Not available'}")

if __name__ == "__main__":
    main()
