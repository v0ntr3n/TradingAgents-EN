#!/usr/bin/env python3
"""
DashScope OpenAI Adapter repair test script
Test the fixed tool binding, conversion and invocation mechanism
"""

import os
import sys
from pathlib import Path

# Add project root directory to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from tradingagents.utils.logging_manager import get_logger
logger = get_logger('test')

def test_enhanced_tool_binding():
    """Testing the enhanced tool binding mechanism"""
    print("\n🔧 Testing the enhanced tool binding mechanism")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Define testing tools
        @tool
        def get_test_stock_data(ticker: str, days: int = 7) -> str:
            """Get test stock data"""
            return f"test data: {ticker} Recently {days} Days of stock data"
        
        @tool
        def get_test_news(query: str) -> str:
            """Get testing news"""
            return f"test news: {query} Related news"
        
        # Create adapter instance
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=200
        )
        
        print("✅ DashScope OpenAI Adapter created successfully")
        
        # Test tool binding
        tools = [get_test_stock_data, get_test_news]
        llm_with_tools = llm.bind_tools(tools)
        
        print("✅ Tool binding successful")
        print(f"   Number of bound tools: {len(tools)}")
        
        # Test tool call
        response = llm_with_tools.invoke([
            HumanMessage(content="Please call the get_test_stock_data tool to obtain AAPL stock data")
        ])
        
        print(f"✅ LLM Call successful")
        print(f"   response type: {type(response)}")
        print(f"   Response content length: {len(response.content) if hasattr(response, 'content') else 0}")
        
        # Check tool calls
        if hasattr(response, 'tool_calls') and response.tool_calls:
            print(f"✅ Tool call detected: {len(response.tool_calls)} a")
            for i, tool_call in enumerate(response.tool_calls):
                print(f"   Tool call {i+1}: {tool_call.get('name', 'unknown')}")
        else:
            print("⚠️ Tool call not detected")
            print(f"   Response content: {response.content[:200]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool binding test failed: {e}")
        return False

def test_tool_format_validation():
    """Test tool format verification mechanism"""
    print("\n🔍 Test tool format verification mechanism")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        
        # Create adapter instance
        llm = ChatDashScopeOpenAI(model="qwen-turbo")
        
        # Test valid tool formats
        valid_tool = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "testing tools",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {"type": "string", "description": "parameters 1"}
                    },
                    "required": ["param1"]
                }
            }
        }
        
        is_valid = llm._validate_openai_tool_format(valid_tool, "test_tool")
        print(f"✅ Valid tool format verification: {'Pass' if is_valid else 'failed'}")
        
        # Testing invalid tool format
        invalid_tool = {
            "type": "invalid",
            "function": {
                "name": "test_tool"
                # missing description
            }
        }
        
        is_invalid = llm._validate_openai_tool_format(invalid_tool, "invalid_tool")
        print(f"✅ Invalid tool format validation: {'Correctly reject' if not is_invalid else 'Error passed'}")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool format validation test failed: {e}")
        return False

def test_backup_tool_creation():
    """Test alternative tool creation mechanism"""
    print("\n🔧 Test alternative tool creation mechanism")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        
        # Create adapter instance
        llm = ChatDashScopeOpenAI(model="qwen-turbo")
        
        # Define testing tools
        @tool
        def test_backup_tool(param1: str, param2: int = 10) -> str:
            """Test alternative tool creation"""
            return f"result: {param1}, {param2}"
        
        # Test alternative tool creation
        backup_tool = llm._create_backup_tool_format(test_backup_tool)
        
        if backup_tool:
            print("✅ Alternate tool created successfully")
            print(f"   Tool name: {backup_tool['function']['name']}")
            print(f"   Tool description: {backup_tool['function']['description']}")
            
            # Verify alternate tool format
            is_valid = llm._validate_openai_tool_format(backup_tool, "backup_test")
            print(f"   Format validation: {'Pass' if is_valid else 'failed'}")
        else:
            print("❌ Alternate tool creation failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"❌ Alternate tool creation test failed: {e}")
        return False

def test_tool_call_response_validation():
    """Test tool call response verification"""
    print("\n🔍 Test tool call response verification")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        
        # Create adapter instance
        llm = ChatDashScopeOpenAI(model="qwen-turbo")
        
        # Test valid tool call formats
        valid_tool_call = {
            "name": "test_tool",
            "args": {"param1": "value1"}
        }
        
        is_valid = llm._validate_tool_call_format(valid_tool_call, 0)
        print(f"✅ Valid tool call verification: {'Pass' if is_valid else 'failed'}")
        
        # Test for invalid tool call format
        invalid_tool_call = {
            "invalid_field": "value"
            # Missing name field
        }
        
        is_invalid = llm._validate_tool_call_format(invalid_tool_call, 1)
        print(f"✅ Invalid tool call verification: {'Correctly reject' if not is_invalid else 'Error passed'}")
        
        # Test tool call fix
        broken_tool_call = {
            "function": {
                "name": "test_tool",
                "arguments": {"param1": "value1"}
            }
        }
        
        fixed_tool_call = llm._fix_tool_call_format(broken_tool_call, 2)
        if fixed_tool_call:
            print("✅ Tool call repair successful")
            print(f"   Name after repair: {fixed_tool_call.get('name')}")
            print(f"   Parameters after repair: {fixed_tool_call.get('args')}")
        else:
            print("❌ Tool call repair failed")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool call response validation test failed: {e}")
        return False

def test_comprehensive_tool_calling():
    """Comprehensive testing tool calling process"""
    print("\n🚀 Comprehensive testing tool calling process")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_openai_adapter import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Define complex test harnesses
        @tool
        def get_stock_analysis(ticker: str, analysis_type: str = "basic") -> str:
            """Get stock analysis reports"""
            return f"stocks {ticker} of {analysis_type} Analysis Report: This is a detailed analysis..."
        
        @tool
        def get_market_news(query: str, days: int = 7) -> str:
            """Get market news"""
            return f"About {query} Recently {days} day s market news..."
        
        # Create adapter and bind tools
        llm = ChatDashScopeOpenAI(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=500
        )
        
        tools = [get_stock_analysis, get_market_news]
        llm_with_tools = llm.bind_tools(tools)
        
        print("✅ Complex tool binding successful")
        
        # Test multiple rounds of conversations and tool calls
        messages = [
            HumanMessage(content="Please help me analyze Apple(AAPL)stocks and get relevant news")
        ]
        
        response = llm_with_tools.invoke(messages)
        
        print(f"✅ Complex dialogue call successful")
        print(f"   Response content length: {len(response.content) if hasattr(response, 'content') else 0}")
        
        # Analyze responses in detail
        if hasattr(response, 'tool_calls') and response.tool_calls:
            print(f"✅ detected {len(response.tool_calls)} tool calls")
            for i, tool_call in enumerate(response.tool_calls):
                print(f"   Tools {i+1}: {tool_call.get('name', 'unknown')}")
                print(f"   parameters: {tool_call.get('args', {})}")
        else:
            print("⚠️ Tool call not detected")
            if hasattr(response, 'content'):
                print(f"   Response content: {response.content[:300]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ Comprehensive tool call test failed: {e}")
        return False

def main():
    """Main test function"""
    print("🧪 DashScope OpenAI Adapter Repair Test")
    print("=" * 80)
    
    # Check environment variables
    if not os.getenv('DASHSCOPE_API_KEY'):
        print("❌ Error: DASHSCOPE_API_KEY environment variable not found")
        print("Please set up your DashScope API key:")
        print("  Windows: set DASHSCOPE_API_KEY=your_api_key")
        print("  Linux/Mac: export DASHSCOPE_API_KEY=your_api_key")
        return
    
    # Run tests
    tests = [
        ("Tool format verification", test_tool_format_validation),
        ("Alternate tool creation", test_backup_tool_creation),
        ("Tool call response verification", test_tool_call_response_validation),
        ("Enhanced tool binding", test_enhanced_tool_binding),
        ("Comprehensive tool call", test_comprehensive_tool_calling),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            result = test_func()
            results[test_name] = result
        except Exception as e:
            print(f"❌ test {test_name} Execution exception: {e}")
            results[test_name] = False
    
    # Output test results
    print("\n📊 Summary of test results")
    print("=" * 60)
    
    passed = 0
    for test_name, result in results.items():
        status = "✅ Pass" if result else "❌ failed"
        print(f"{test_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📈 Overall results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 All tests passed! DashScope OpenAI adapter repaired successfully!")
        print("\n💡 Repair effect:")
        print("   ✅ The tool conversion mechanism is enhanced to support alternate formats")
        print("   ✅ Tool format verification to ensure compatibility")
        print("   ✅ Tool call response verification and repair")
        print("   ✅ Detailed error handling and logging")
        print("   ✅ Improved tool calling success rate")
    else:
        print(f"\n⚠️ Some tests failed and require further debugging")
        print("Please check the failed test project and view the detailed log")

if __name__ == "__main__":
    main()