#!/usr/bin/env python3
"""
Alibaba Bailian Tool Call Test - Agent friendly version
Specifically optimized for agent execution to avoid crash issues
"""

import os
import sys
import time
import traceback

# Force refresh output
def flush_print(msg):
    """Force refresh output"""
    print(msg)
    sys.stdout.flush()
    time.sleep(0.1)  # Give the agent time to capture the output

def main():
    """Main test function"""
    flush_print("🔬 Alibaba Bailian Tool Call Test - Agent friendly version")
    flush_print("=" * 60)
    
    try:
        # Add project root directory to Python path
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        flush_print("✅ Project path configuration completed")
        
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            flush_print("❌ DASHSCOPE_API_KEY environment variable not found")
            return False
        
        flush_print(f"✅ API Key configured: {api_key[:10]}...")
        
        # test 1: Basic import
        flush_print("\n🔧 test 1: Basic import")
        flush_print("-" * 40)
        
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        flush_print("✅ All modules imported successfully")
        
        # test 2: LLM Create
        flush_print("\n🔧 test 2: LLM Create")
        flush_print("-" * 40)
        
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=200
        )
        
        flush_print("✅ LLM Instance created successfully")
        
        # test 3: Tool definition and binding
        flush_print("\n🔧 test 3: Tool definition and binding")
        flush_print("-" * 40)
        
        @tool
        def get_stock_info(symbol: str) -> str:
            """Get stock information"""
            return f"stocks{symbol}information: Price 100 yuan, increase+2.5%"
        
        llm_with_tools = llm.bind_tools([get_stock_info])
        flush_print("✅ Tool binding successful")
        
        # test 4: Simple call (no tool call required)
        flush_print("\n🔧 test 4: simple call")
        flush_print("-" * 40)
        
        simple_response = llm.invoke([
            HumanMessage(content="Please simply reply: Hello")
        ])
        
        flush_print(f"✅ Simple call successful")
        flush_print(f"   response length: {len(simple_response.content)}character")
        flush_print(f"   Response content: {simple_response.content}")
        
        # test 5: Tool call test
        flush_print("\n🔧 test 5: Tool call test")
        flush_print("-" * 40)
        
        # Try multiple prompt strategies
        prompts = [
            "Please call the get_stock_info tool to query AAPL stock information",
            "I need stock information for AAPL, please use the available tools",
            "The get_stock_info tool must be called with parameters symbol='AAPL'"
        ]
        
        tool_call_success = False
        
        for i, prompt in enumerate(prompts, 1):
            flush_print(f"\n   Strategy{i}: {prompt[:30]}...")
            
            try:
                response = llm_with_tools.invoke([HumanMessage(content=prompt)])
                
                tool_calls = getattr(response, 'tool_calls', [])
                flush_print(f"   Number of tool calls: {len(tool_calls)}")
                flush_print(f"   response length: {len(response.content)}character")
                
                if len(tool_calls) > 0:
                    flush_print(f"   ✅ Strategy{i}success: Tool call triggered")
                    for j, tool_call in enumerate(tool_calls):
                        tool_name = tool_call.get('name', 'unknown')
                        tool_args = tool_call.get('args', {})
                        flush_print(f"      Tools{j+1}: {tool_name}({tool_args})")
                    tool_call_success = True
                    break
                else:
                    flush_print(f"   ❌ Strategy{i}failed: Tool call not triggered")
                    flush_print(f"   direct response: {response.content[:100]}...")
                    
            except Exception as e:
                flush_print(f"   ❌ Strategy{i}Abnormal: {e}")
        
        # test 6: Different model testing
        flush_print("\n🔧 test 6: Different model testing")
        flush_print("-" * 40)
        
        models = ["qwen-turbo", "qwen-plus-latest"]
        
        for model in models:
            flush_print(f"\n   test model: {model}")
            
            try:
                test_llm = ChatDashScopeOpenAI(
                    model=model,
                    temperature=0.0,  # lower temperature
                    max_tokens=100
                )
                
                test_llm_with_tools = test_llm.bind_tools([get_stock_info])
                
                response = test_llm_with_tools.invoke([
                    HumanMessage(content="Please call the get_stock_info tool to query TSLA")
                ])
                
                tool_calls = getattr(response, 'tool_calls', [])
                flush_print(f"   {model}: Number of tool calls = {len(tool_calls)}")
                
                if len(tool_calls) > 0:
                    flush_print(f"   ✅ {model}: Support tool calling")
                else:
                    flush_print(f"   ❌ {model}: Tool calling is not supported")
                    
            except Exception as e:
                flush_print(f"   ❌ {model}: Test exception - {str(e)[:100]}")
        
        # Summary
        flush_print("\n📋 Test summary")
        flush_print("=" * 50)
        
        if tool_call_success:
            flush_print("🎉 Alibaba Bailian tool call test was successful!")
            flush_print("   ✅ The model is able to understand and execute tool calls")
            flush_print("   ✅ OpenAI Compatible adapters work fine")
        else:
            flush_print("⚠️ There is a problem in calling Alibaba Bailian tool")
            flush_print("   ❌ The model does not actively call tools")
            flush_print("   💡 Suggestions: Use manual tool calls as a fallback")
        
        flush_print("\n🔍 Problem analysis:")
        flush_print("   1. Adapter creation: ✅ normal")
        flush_print("   2. Tool binding: ✅ normal")
        flush_print("   3. API call: ✅ normal")
        flush_print(f"   4. Tool call: {'✅ normal' if tool_call_success else '❌ Abnormal'}")
        
        if not tool_call_success:
            flush_print("\n💡 solution:")
            flush_print("   1. Use more explicit tool calling instructions")
            flush_print("   2. Adjust model parameters(temperature=0.0)")
            flush_print("   3. Calling a pattern using hand tools")
            flush_print("   4. Consider using DeepSeek as an alternative")
        
        return tool_call_success
        
    except Exception as e:
        flush_print(f"\n💥 Test exception: {e}")
        flush_print("Exception details:")
        traceback.print_exc()
        return False
    
    finally:
        flush_print("\n" + "="*60)
        flush_print("Test completed!")
        # Not used input()avoid hangs

if __name__ == "__main__":
    try:
        success = main()
        exit_code = 0 if success else 1
        flush_print(f"exit code: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        flush_print(f"Main function exception: {e}")
        sys.exit(1)
