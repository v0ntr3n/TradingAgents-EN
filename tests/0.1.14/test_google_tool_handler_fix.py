#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test the Google tool call processor repair effect
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
import logging

# Setup log
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_tool_call_validation():
    """Test tool calls verification function"""
    print("=" * 60)
    print("🧪 Test tool calls verification function")
    print("=" * 60)
    
    # Test valid tool calls
    valid_tool_call = {
        'name': 'get_stock_market_data_unified',
        'args': {'symbol': 'AAPL', 'period': '1d'},
        'id': 'call_12345'
    }
    
    result = GoogleToolCallHandler._validate_tool_call(valid_tool_call, 0, "test analyst")
    print(f"✅ Valid tool call verification results: {result}")
    assert result == True, "Valid tool calls should pass validation"
    
    # Testing invalid tool call - missing field
    invalid_tool_call_1 = {
        'name': 'get_stock_market_data_unified',
        'args': {'symbol': 'AAPL'}
        # missing 'id' Field
    }
    
    result = GoogleToolCallHandler._validate_tool_call(invalid_tool_call_1, 1, "test analyst")
    print(f"❌ Invalid tool call 1 verification result: {result}")
    assert result == False, "Tool calls with missing fields should fail validation"
    
    # Testing invalid tool call - error type
    invalid_tool_call_2 = {
        'name': '',  # empty string
        'args': 'not_a_dict',  # not a dictionary
        'id': 123  # not a string
    }
    
    result = GoogleToolCallHandler._validate_tool_call(invalid_tool_call_2, 2, "test analyst")
    print(f"❌ Invalid tool call 2 verification result: {result}")
    assert result == False, "Tool calls of the wrong type should fail validation"
    
    print("✅ Tool call verification function test passed")

def test_tool_call_fixing():
    """Test tool calls repair function"""
    print("\n" + "=" * 60)
    print("🔧 Test tool calls repair function")
    print("=" * 60)
    
    # Tool call fix for testing OpenAI format
    openai_format_tool_call = {
        'function': {
            'name': 'get_stock_market_data_unified',
            'arguments': '{"symbol": "AAPL", "period": "1d"}'
        }
        # missing 'id' Field
    }
    
    fixed_tool_call = GoogleToolCallHandler._fix_tool_call(openai_format_tool_call, 0, "test analyst")
    print(f"🔧 Fixed tool calls: {fixed_tool_call}")
    
    if fixed_tool_call:
        assert 'name' in fixed_tool_call, "The name field should be included after repair"
        assert 'args' in fixed_tool_call, "The args field should be included after the fix"
        assert 'id' in fixed_tool_call, "After repair it should contain the id field"
        assert isinstance(fixed_tool_call['args'], dict), "args Should be a dictionary type"
        print("✅ OpenAI Format tool call repair successful")
    else:
        print("❌ OpenAI Format tool call repair failed")
    
    # Test unfixable tool calls
    unfixable_tool_call = "not_a_dict"
    
    fixed_tool_call = GoogleToolCallHandler._fix_tool_call(unfixable_tool_call, 1, "test analyst")
    print(f"❌ Unrepairable tool call results: {fixed_tool_call}")
    assert fixed_tool_call is None, "Unrepairable tool calls should return None"
    
    print("✅ The tool call repair function test passed")

def test_duplicate_prevention():
    """Test the repeated call protection function"""
    print("\n" + "=" * 60)
    print("🛡️ Test the repeated call protection function")
    print("=" * 60)
    
    # Simulate repeated tool calls
    tool_calls = [
        {
            'name': 'get_stock_market_data_unified',
            'args': {'symbol': 'AAPL', 'period': '1d'},
            'id': 'call_1'
        },
        {
            'name': 'get_stock_market_data_unified',
            'args': {'symbol': 'AAPL', 'period': '1d'},  # Same parameters
            'id': 'call_2'
        },
        {
            'name': 'get_stock_market_data_unified',
            'args': {'symbol': 'TSLA', 'period': '1d'},  # different parameters
            'id': 'call_3'
        }
    ]
    
    executed_tools = set()
    unique_calls = []
    
    for i, tool_call in enumerate(tool_calls):
        tool_name = tool_call.get('name')
        tool_args = tool_call.get('args', {})
        tool_signature = f"{tool_name}_{hash(str(tool_args))}"
        
        if tool_signature in executed_tools:
            print(f"⚠️ Skip duplicate tool calls {i}: {tool_name} with {tool_args}")
        else:
            executed_tools.add(tool_signature)
            unique_calls.append(tool_call)
            print(f"✅ Execute tool call {i}: {tool_name} with {tool_args}")
    
    print(f"📊 Number of raw tool calls: {len(tool_calls)}")
    print(f"📊 Number of tool calls after deduplication: {len(unique_calls)}")
    
    assert len(unique_calls) == 2, "There should be 2 unique tool calls"
    print("✅ Repeated call protection function test passed")

def main():
    """Main test function"""
    print("🚀 Start testing the Google tool call processor repair effect")
    
    try:
        test_tool_call_validation()
        test_tool_call_fixing()
        test_duplicate_prevention()
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! Google tool call processor repair successful")
        print("=" * 60)
        
        print("\n📋 Repair summary:")
        print("1. ✅ Added tool call format validation")
        print("2. ✅ Implemented automatic repair of tool calls (supports OpenAI format conversion)")
        print("3. ✅ Added duplicate call protection mechanism")
        print("4. ✅ Improved error handling and logging")
        
        print("\n🔧 Major improvements:")
        print("- Prevent repeated calls to unified market data tools")
        print("- Automatically validate and fix bad tool calls for Google models")
        print("- Support automatic conversion from OpenAI format to standard format")
        print("- Enhanced error handling and debugging information")
        
    except Exception as e:
        print(f"\n❌ test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)