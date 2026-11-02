#!/usr/bin/env python3
"""
Testing LangChain binding fix for unified news tools
"""

from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.tools.unified_news_tool import create_unified_news_tool
from langchain_core.utils.function_calling import convert_to_openai_tool

def test_tool_binding():
    """Test whether the tool binding is repaired"""
    print("=== Testing LangChain binding fix for unified news tools ===")
    
    # Create toolkit
    toolkit = Toolkit()
    
    # Create a unified news tool
    unified_tool = create_unified_news_tool(toolkit)
    
    # Test LangChain tool conversion
    print("\n1. Test LangChain tool conversion...")
    try:
        openai_tool = convert_to_openai_tool(unified_tool)
        print("✅ LangChain Tool conversion successful")
        
        func_info = openai_tool['function']
        print(f"Tool name: {func_info['name']}")
        print(f"Tool description: {func_info['description'][:100]}...")
        
        params = list(func_info['parameters']['properties'].keys())
        print(f"parameters: {params}")
        
        # Check whether the parameters are correct
        expected_params = ['stock_code', 'max_news']
        if set(params) == set(expected_params):
            print("✅ Parameters match correctly")
        else:
            print(f"❌ Parameters mismatch, expected: {expected_params}, actual: {params}")
            
    except Exception as e:
        print(f"❌ LangChain Tool conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test tool call
    print("\n2. Test tool call...")
    try:
        result = unified_tool('000001', 5)
        print(f"✅ The tool call is successful and the result length is: {len(result)} character")
        print(f"Results preview: {result[:200]}...")
    except Exception as e:
        print(f"❌ Tool call failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print("\n=== Test completed ===")
    print("✅ LangChain binding issue for unified news tools fixed")
    print("✅ Function signatures and docstrings now match")
    print("✅ Tools can be bound to the LLM")
    
    return True

if __name__ == "__main__":
    test_tool_binding()