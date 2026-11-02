#!/usr/bin/env python3
"""
Debugging tool binding issues
Verify that LLM can access unbound tools
"""

import os
import sys

def test_tool_isolation():
    """Test tool isolation mechanism"""
    print("🔧 Test tool isolation mechanism...")
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY not found, test skipped")
            return True
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Create LLM
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=200
        )
        
        print(f"\n📋 All tools in the toolkit:")
        all_tools = []
        for attr_name in dir(toolkit):
            if not attr_name.startswith('_') and callable(getattr(toolkit, attr_name)):
                attr = getattr(toolkit, attr_name)
                if hasattr(attr, 'name'):
                    all_tools.append(attr.name)
                    print(f"  - {attr.name}")
        
        print(f"\n🔧 test 1: Only bind Hong Kong stock instruments")
        hk_tools = [toolkit.get_hk_stock_data_unified]
        llm_hk = llm.bind_tools(hk_tools)
        
        print(f"  Bound tools: {[tool.name for tool in hk_tools]}")
        
        # Test whether other tools can be called
        test_message = HumanMessage(content="Please call the get_fundamentals_openai tool to obtain the data of 0700.HK")
        
        try:
            response = llm_hk.invoke([test_message])
            print(f"  response type: {type(response)}")
            print(f"  Number of tool calls: {len(getattr(response, 'tool_calls', []))}")
            
            if hasattr(response, 'tool_calls') and response.tool_calls:
                called_tools = [call.get('name', 'unknown') for call in response.tool_calls]
                print(f"  The actual tool called: {called_tools}")
                
                # Check if unbound tools are called
                unexpected_tools = [tool for tool in called_tools if tool not in [t.name for t in hk_tools]]
                if unexpected_tools:
                    print(f"  ❌ Unbound tool called: {unexpected_tools}")
                    return False
                else:
                    print(f"  ✅ Only the bound tools are called")
            else:
                print(f"  ℹ️ No tool calls")
                
        except Exception as e:
            print(f"  ❌ call failed: {e}")
            return False
        
        print(f"\n🔧 test 2: Create a new LLM instance")
        llm2 = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=200
        )
        
        china_tools = [toolkit.get_china_stock_data]
        llm2_china = llm2.bind_tools(china_tools)
        
        print(f"  Bound tools: {[tool.name for tool in china_tools]}")
        
        test_message2 = HumanMessage(content="Please call the get_hk_stock_data_unified tool to obtain the data of 0700.HK")
        
        try:
            response2 = llm2_china.invoke([test_message2])
            print(f"  response type: {type(response2)}")
            print(f"  Number of tool calls: {len(getattr(response2, 'tool_calls', []))}")
            
            if hasattr(response2, 'tool_calls') and response2.tool_calls:
                called_tools2 = [call.get('name', 'unknown') for call in response2.tool_calls]
                print(f"  The actual tool called: {called_tools2}")
                
                # Check if unbound tools are called
                unexpected_tools2 = [tool for tool in called_tools2 if tool not in [t.name for t in china_tools]]
                if unexpected_tools2:
                    print(f"  ❌ Unbound tool called: {unexpected_tools2}")
                    return False
                else:
                    print(f"  ✅ Only the bound tools are called")
            else:
                print(f"  ℹ️ No tool calls")
                
        except Exception as e:
            print(f"  ❌ call failed: {e}")
            return False
        
        print(f"\n✅ Tool isolation testing completed")
        return True
        
    except Exception as e:
        print(f"❌ Tool isolation test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_llm_instance_reuse():
    """Testing LLM instance reuse issues"""
    print("\n🔧 Test LLM instance reuse...")
    
    try:
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.default_config import DEFAULT_CONFIG
        
        # Create toolkit
        config = DEFAULT_CONFIG.copy()
        config["online_tools"] = True
        toolkit = Toolkit(config)
        
        # Check if global LLM instance exists
        print(f"  Check LLM instance creation...")
        
        llm1 = ChatDashScopeOpenAI(model="qwen-turbo")
        llm2 = ChatDashScopeOpenAI(model="qwen-turbo")
        
        print(f"  LLM1 ID: {id(llm1)}")
        print(f"  LLM2 ID: {id(llm2)}")
        print(f"  Is it the same instance?: {llm1 is llm2}")
        
        # Check tool binding status
        tools1 = [toolkit.get_hk_stock_data_unified]
        tools2 = [toolkit.get_china_stock_data]
        
        llm1_with_tools = llm1.bind_tools(tools1)
        llm2_with_tools = llm2.bind_tools(tools2)
        
        print(f"  LLM1 binding tool: {[t.name for t in tools1]}")
        print(f"  LLM2 binding tool: {[t.name for t in tools2]}")
        
        # Check the bound instance
        print(f"  LLM1 After binding ID: {id(llm1_with_tools)}")
        print(f"  LLM2 After binding ID: {id(llm2_with_tools)}")
        
        return True
        
    except Exception as e:
        print(f"❌ LLM Instance reuse test failed: {e}")
        return False


def main():
    """Main test function"""
    print("🔧 Debugging tool binding issues")
    print("=" * 60)
    
    tests = [
        test_llm_instance_reuse,
        test_tool_isolation,
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                print(f"❌ test failed: {test.__name__}")
        except Exception as e:
            print(f"❌ Test exception: {test.__name__} - {e}")
    
    print("\n" + "=" * 60)
    print(f"📊 Test results: {passed}/{total} Pass")
    
    if passed == total:
        print("🎉 All tests passed!")
        return True
    else:
        print("⚠️ Some tests failed and require further inspection")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
