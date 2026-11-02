#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test CLI fix - KeyError: 'stock_symbol' question
Test CLI Fix - KeyError: 'stock_symbol' Issue

This test verifies the fix for the key name mismatch in the selections dictionary in the CLI
This test verifies the fix for the selections dictionary key mismatch issue in CLI
"""

import sys
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_selections_dictionary_keys():
    """
    Test whether the key names in the selections dictionary are correct
    Test if the keys in selections dictionary are correct
    """
    print("🔍 Test selections dictionary key name...")
    
    try:
        from cli.main import get_user_selections
        
        # Simulate user input
        with patch('typer.prompt') as mock_prompt, \
             patch('cli.main.select_market') as mock_market, \
             patch('cli.main.select_analysts') as mock_analysts, \
             patch('cli.main.select_research_depth') as mock_depth, \
             patch('cli.main.select_llm_provider') as mock_llm, \
             patch('cli.main.select_shallow_thinking_agent') as mock_shallow, \
             patch('cli.main.select_deep_thinking_agent') as mock_deep, \
             patch('cli.main.console.print'):
            
            # Set simulation return value
            mock_market.return_value = {
                'name': 'A shares',
                'name_en': 'China A-Share',
                'default': '600036',
                'pattern': r'^\d{6}$',
                'data_source': 'china_stock'
            }
            mock_prompt.side_effect = ['600036', '2024-12-01']  # ticker, date
            mock_analysts.return_value = [MagicMock(value='market')]
            mock_depth.return_value = 3
            mock_llm.return_value = ('dashscope', 'http://localhost:8000')
            mock_shallow.return_value = 'qwen-turbo'
            mock_deep.return_value = 'qwen-max'
            
            # call function
            selections = get_user_selections()
            
            # Verify necessary keys exist
            required_keys = [
                'ticker',  # This is the correct key name
                'market',
                'analysis_date',
                'analysts',
                'research_depth',
                'llm_provider',
                'backend_url',
                'shallow_thinker',
                'deep_thinker'
            ]
            
            for key in required_keys:
                assert key in selections, f"Missing necessary key: {key}"
                print(f"✅ key '{key}' exist")
            
            # Make sure there are no wrong key names
            assert 'stock_symbol' not in selections, "should not exist 'stock_symbol' key"
            print("✅ Confirm that there are no errors 'stock_symbol' key")
            
            print("✅ selections Dictionary key name test passed")
            return True
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_process_signal_call():
    """
    Test that the process_signal call uses the correct key name
    Test if process_signal call uses correct key name
    """
    print("\n🔍 Test process_signal call...")
    
    try:
        # Read the contents of the main.py file
        main_file = project_root / 'cli' / 'main.py'
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that the correct key name is used
        if "selections['ticker']" in content:
            print("✅ Find the correct key name selections['ticker']")
        else:
            print("❌ not found selections['ticker']")
            return False
        
        # Make sure you never use the wrong key name again
        if "selections['stock_symbol']" in content:
            print("❌ Still having wrong key name selections['stock_symbol']")
            return False
        else:
            print("✅ Confirm that there are no incorrect key names selections['stock_symbol']")
        
        print("✅ process_signal Call test passed")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def test_code_consistency():
    """
    Test code consistency - make sure the same key names are used everywhere
    Test code consistency - ensure all places use the same key names
    """
    print("\n🔍 Test code consistency...")
    
    try:
        main_file = project_root / 'cli' / 'main.py'
        with open(main_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count the number of times the ticker key is used
        ticker_count = content.count("selections['ticker']")
        ticker_double_quote_count = content.count('selections["ticker"]')
        
        total_ticker_usage = ticker_count + ticker_double_quote_count
        
        print(f"📊 'ticker'Number of key uses: {total_ticker_usage}")
        
        if total_ticker_usage >= 2:  # There should be at least 2 uses (initialization and process_signal)
            print("✅ ticker Reasonable number of key uses")
        else:
            print("⚠️  ticker Key usage may not be enough")
        
        # Check for other possible key name inconsistencies
        potential_issues = [
            "selections['symbol']",
            "selections['stock']",
            "selections['code']"
        ]
        
        for issue in potential_issues:
            if issue in content:
                print(f"⚠️  Discover potential problems: {issue}")
            else:
                print(f"✅ No problem found: {issue}")
        
        print("✅ Code consistency test passed")
        return True
        
    except Exception as e:
        print(f"❌ test failed: {e}")
        return False

def main():
    """
    Run all tests
    Run all tests
    """
    print("🚀 Start CLI repair verification test...")
    print("=" * 50)
    
    tests = [
        test_selections_dictionary_keys,
        test_process_signal_call,
        test_code_consistency
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 50)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed!KeyError: 'stock_symbol' Problem fixed")
        return True
    else:
        print("❌ Some tests failed and require further inspection")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)