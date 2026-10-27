#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Document consistency testing
Documentation Consistency Test

Test whether the configuration and instructions in the document are consistent
Test if configurations and descriptions in documentation are consistent
"""

import os
import re
import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_redis_commander_port_consistency():
    """
    Test the consistency of Redis Commander port configuration
    Test Redis Commander port configuration consistency
    """
    print("🔍 Test Redis Commander port configuration consistency...")
    
    # Check the .env.example file
    env_example_path = project_root / ".env.example"
    if env_example_path.exists():
        with open(env_example_path, 'r', encoding='utf-8') as f:
            env_content = f.read()
            # Should contain port 8082
            if "localhost:8082" in env_content and "Redis Commander" in env_content:
                print("✅ .env.example The Redis Commander port configuration is correct (8082)")
            else:
                print("❌ .env.example Incorrect Redis Commander port configuration")
                return False
    
    # Check the database_setup.md file
    db_setup_path = project_root / "docs" / "database_setup.md"
    if db_setup_path.exists():
        with open(db_setup_path, 'r', encoding='utf-8') as f:
            db_content = f.read()
            # Should contain port 8082
            if "8082" in db_content and "Redis Commander" in db_content:
                print("✅ database_setup.md The Redis Commander port configuration is correct (8082)")
            else:
                print("❌ database_setup.md Incorrect Redis Commander port configuration")
                return False
    
    return True


def test_cli_command_format_consistency():
    """
    Test CLI command format consistency
    Test CLI command format consistency
    """
    print("\n🔍 Test CLI command format consistency...")
    
    # Check main documentation files
    docs_to_check = [
        "README-CN.md",
        "docs/configuration/google-ai-setup.md"
    ]
    
    for doc_file in docs_to_check:
        doc_path = project_root / doc_file
        if doc_path.exists():
            with open(doc_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
                # Check that the recommended python -m cli.main format is used
                old_format_count = len(re.findall(r'python cli/main\.py', content))
                new_format_count = len(re.findall(r'python -m cli\.main', content))
                
                if old_format_count == 0:
                    print(f"✅ {doc_file} The CLI command format is correct")
                else:
                    print(f"❌ {doc_file} There are still {old_format_count} Use old format everywhere")
                    return False
    
    return True


def test_cli_smart_suggestions():
    """
    Testing the CLI Smart Suggestions feature
    Test CLI smart suggestions feature
    """
    print("\n🔍 Testing the CLI Smart Suggestions feature...")
    
    # Check cli/main.py for smart suggestion code
    cli_main_path = project_root / "cli" / "main.py"
    if cli_main_path.exists():
        with open(cli_main_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
            # Check whether smart suggestion related code is included
            if "get_close_matches" in content and "Do you want to use one of the following commands" in content:
                print("✅ CLI Smart suggestion function has been implemented")
                return True
            else:
                print("❌ CLI Smart suggestion feature not found")
                return False
    
    return False


def test_documentation_structure():
    """
    Test the integrity of the document structure
    Test documentation structure completeness
    """
    print("\n🔍 Test document structural integrity...")
    
    # Check if key documents exist
    key_docs = [
        "README.md",
        "docs/README.md",
        "docs/database_setup.md",
        "docs/overview/quick-start.md",
        "docs/configuration/data-directory-configuration.md"
    ]
    
    missing_docs = []
    for doc in key_docs:
        doc_path = project_root / doc
        if not doc_path.exists():
            missing_docs.append(doc)
    
    if not missing_docs:
        print("✅ All key documents are present")
        return True
    else:
        print(f"❌ missing documentation: {', '.join(missing_docs)}")
        return False


def main():
    """
    Main test function
    Main test function
    """
    print("🚀 Start document consistency testing...")
    print("=" * 50)
    
    tests = [
        test_redis_commander_port_consistency,
        test_cli_command_format_consistency,
        test_cli_smart_suggestions,
        test_documentation_structure
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ test {test_func.__name__} Execution failed: {e}")
    
    print("\n" + "=" * 50)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All document consistency tests passed!")
        return True
    else:
        print("⚠️ Some tests failed, please check the above issues")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)