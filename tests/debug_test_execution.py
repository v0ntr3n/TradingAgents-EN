#!/usr/bin/env python3
"""
Test execution diagnostic script
Step by step check the reasons why the test script crashes
"""

import sys
import os
import traceback

def step1_basic_check():
    """steps 1: Basic environmental check"""
    print("🔍 steps 1: Basic environmental check")
    print("-" * 40)
    
    try:
        print(f"✅ Python version: {sys.version}")
        print(f"✅ Python path: {sys.executable}")
        print(f"✅ working directory: {os.getcwd()}")
        print(f"✅ virtual environment: {os.environ.get('VIRTUAL_ENV', 'Not activated')}")
        return True
    except Exception as e:
        print(f"❌ Basic check failed: {e}")
        return False

def step2_path_check():
    """steps 2: path check"""
    print("\n🔍 steps 2: path check")
    print("-" * 40)
    
    try:
        # Check the project root directory
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        print(f"✅ Project root directory: {project_root}")
        
        # Check key directory
        key_dirs = ['tradingagents', 'tests', 'cli']
        for dir_name in key_dirs:
            dir_path = os.path.join(project_root, dir_name)
            if os.path.exists(dir_path):
                print(f"✅ {dir_name}Directory: exist")
            else:
                print(f"❌ {dir_name}Directory: does not exist")
        
        # Add to Python path
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
            print(f"✅ Added project root directory to Python path")
        
        return True
    except Exception as e:
        print(f"❌ Path check failed: {e}")
        traceback.print_exc()
        return False

def step3_import_check():
    """steps 3: Import check"""
    print("\n🔍 steps 3: Import check")
    print("-" * 40)
    
    imports = [
        ("langchain_core.messages", "HumanMessage"),
        ("langchain_core.tools", "tool"),
        ("tradingagents.llm_adapters", "ChatDashScopeOpenAI"),
        ("tradingagents.config.config_manager", "token_tracker")
    ]
    
    success_count = 0
    for module, item in imports:
        try:
            exec(f"from {module} import {item}")
            print(f"✅ {module}.{item}: Import successful")
            success_count += 1
        except ImportError as e:
            print(f"❌ {module}.{item}: Import failed - {e}")
        except Exception as e:
            print(f"⚠️ {module}.{item}: Import exception - {e}")
    
    print(f"\n📊 Import results: {success_count}/{len(imports)} success")
    return success_count == len(imports)

def step4_env_check():
    """steps 4: Environment variable check"""
    print("\n🔍 steps 4: Environment variable check")
    print("-" * 40)
    
    try:
        # Check key environment variables
        env_vars = [
            "DASHSCOPE_API_KEY",
            "TUSHARE_TOKEN",
            "OPENAI_API_KEY"
        ]
        
        for var in env_vars:
            value = os.getenv(var)
            if value:
                print(f"✅ {var}: Already set ({value[:10]}...)")
            else:
                print(f"⚠️ {var}: not set")
        
        return True
    except Exception as e:
        print(f"❌ Environment variable check failed: {e}")
        return False

def step5_simple_llm_test():
    """steps 5: Simple LLM test"""
    print("\n🔍 steps 5: Simple LLM test")
    print("-" * 40)
    
    try:
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY Not set, skips LLM testing")
            return True
        
        print("🔄 Import LLM adapter...")
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        print("✅ LLM Adapter imported successfully")
        
        print("🔄 Create LLM instance...")
        llm = ChatDashScopeOpenAI(
            model="qwen-turbo",
            temperature=0.1,
            max_tokens=50
        )
        print("✅ LLM Instance created successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Simple LLM test fails: {e}")
        traceback.print_exc()
        return False

def step6_tool_binding_test():
    """steps 6: Tool binding test"""
    print("\n🔍 steps 6: Tool binding test")
    print("-" * 40)
    
    try:
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY Not set, skips tool binding testing")
            return True
        
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        
        print("🔄 Define testing tools...")
        @tool
        def test_tool(text: str) -> str:
            """testing tools"""
            return f"tool returns: {text}"
        
        print("🔄 Create LLM and bind tools...")
        llm = ChatDashScopeOpenAI(model="qwen-turbo", max_tokens=50)
        llm_with_tools = llm.bind_tools([test_tool])
        print("✅ Tool binding successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Tool binding test failed: {e}")
        traceback.print_exc()
        return False

def step7_actual_call_test():
    """steps 7: Actual call test"""
    print("\n🔍 steps 7: Actual call test")
    print("-" * 40)
    
    try:
        # Check API key
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            print("⚠️ DASHSCOPE_API_KEY Not set, skips actually calling the test")
            return True
        
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from langchain_core.tools import tool
        from langchain_core.messages import HumanMessage
        
        @tool
        def test_tool(text: str) -> str:
            """testing tools"""
            return f"tool returns: {text}"
        
        print("🔄 Create LLM and bind tools...")
        llm = ChatDashScopeOpenAI(model="qwen-turbo", max_tokens=100)
        llm_with_tools = llm.bind_tools([test_tool])
        
        print("🔄 Send test request...")
        response = llm_with_tools.invoke([
            HumanMessage(content="Please reply: test successful")
        ])
        
        print(f"✅ Call successful")
        print(f"   response type: {type(response)}")
        print(f"   response length: {len(response.content)}character")
        print(f"   Response content: {response.content[:100]}...")
        
        # Check tool calls
        tool_calls = getattr(response, 'tool_calls', [])
        print(f"   Number of tool calls: {len(tool_calls)}")
        
        return True
        
    except Exception as e:
        print(f"❌ The actual call to the test fails: {e}")
        traceback.print_exc()
        return False

def main():
    """Main diagnostic function"""
    print("🔬 Test execution diagnostics")
    print("=" * 60)
    print("💡 target: Find out why the test script crashes")
    print("=" * 60)
    
    # Run all diagnostic steps
    steps = [
        ("Basic environmental check", step1_basic_check),
        ("path check", step2_path_check),
        ("Import check", step3_import_check),
        ("Environment variable check", step4_env_check),
        ("Simple LLM test", step5_simple_llm_test),
        ("Tool binding test", step6_tool_binding_test),
        ("Actual call test", step7_actual_call_test)
    ]
    
    results = []
    for step_name, step_func in steps:
        print(f"\n{'='*60}")
        try:
            result = step_func()
            results.append((step_name, result))
            
            if not result:
                print(f"\n❌ {step_name}Failure, stop subsequent tests")
                break
                
        except Exception as e:
            print(f"\n❌ {step_name}Abnormal: {e}")
            traceback.print_exc()
            results.append((step_name, False))
            break
    
    # Summary
    print(f"\n{'='*60}")
    print("📋 Diagnosis summary")
    print("=" * 60)
    
    passed = 0
    for step_name, result in results:
        status = "✅ Pass" if result else "❌ failed"
        print(f"{step_name}: {status}")
        if result:
            passed += 1
    
    total = len(results)
    print(f"\n📊 Diagnosis results: {passed}/{total} Pass")
    
    if passed == total:
        print("\n🎉 All diagnoses passed!")
        print("The test script should run fine")
    else:
        print(f"\n⚠️ In the first{passed+1}step failed")
        print("Please fix the problem according to the error message")
    
    # Prevent script from crashing
    print("\n" + "="*60)
    print("Diagnosis complete! Press Enter to exit...")
    try:
        input()
    except:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n💥 Main function exception: {e}")
        traceback.print_exc()
        print("\n Press Enter to exit...")
        try:
            input()
        except:
            pass
