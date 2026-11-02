#!/usr/bin/env python3
"""
Test the behavioral differences of different LLM models in terms of tool calling and technical analysis
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
import json

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_deepseek_tool_calling():
    """Test DeepSeek s tool calling behavior"""
    print("🤖 Test DeepSeek tool calling behavior")
    print("=" * 60)

    try:
        # Directly import the DeepSeek adapter to avoid importing dashscope
        import sys
        sys.path.insert(0, str(project_root / "tradingagents" / "llm_adapters"))
        from deepseek_adapter import ChatDeepSeek
        from langchain_core.tools import BaseTool
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create simulated stock data tools
        class MockChinaStockDataTool(BaseTool):
            name: str = "get_china_stock_data"
            description: str = "Get market data and technical indicators for China A-share stock 000002"
            
            def _run(self, query: str = "") -> str:
                return """# 000002 Vanke A stock data analysis

## 📊 Real-time quotes
- Stock name: Vanke A
- current price: ¥6.56
- Increase or decrease: 0.61%
- Volume: 934,783 hand

## 📈 Technical indicators
- 10 day EMA: ¥6.45
- 50 day SMA: ¥6.78
- 200 day SMA: ¥7.12
- RSI: 42.5
- MACD: -0.08
- MACD signal line: -0.12
- Bollinger Bands track: ¥7.20
- Bollinger Bands Middle Track: ¥6.80
- Bollinger Bands Lower Track: ¥6.40
- ATR: 0.25"""
        
        tools = [MockChinaStockDataTool()]
        
        # test prompt word
        prompt = """Please provide a detailed technical analysis of China A-share stock 000002.

Execution steps:
1. Get stock market data using get_china_stock_data tool
2. Conduct in-depth technical indicator analysis based on acquired real data
3. Output the complete technical analysis report content

Important requirements:
- Tools must be called to obtain data
- The complete content of the technical analysis report must be output, do not just describe that the report is completed
- Reports must be analyzed based on real data obtained by the tool"""
        
        # Bind the tool and call
        chain = deepseek_llm.bind_tools(tools)
        result = chain.invoke(prompt)
        
        print(f"📊 DeepSeek response type: {type(result)}")
        print(f"📊 DeepSeek Number of tool calls: {len(result.tool_calls) if hasattr(result, 'tool_calls') else 0}")
        print(f"📊 DeepSeek Response content length: {len(result.content)}")
        print(f"📊 DeepSeek The first 500 characters of the response content:")
        print("-" * 50)
        print(result.content[:500])
        print("-" * 50)
        
        if hasattr(result, 'tool_calls') and result.tool_calls:
            print(f"📊 DeepSeek Tool call details:")
            for i, call in enumerate(result.tool_calls):
                print(f"   Tools{i+1}: {call.get('name', 'unknown')}")
                print(f"   parameters: {call.get('args', {})}")
        
        return result
        
    except Exception as e:
        print(f"❌ DeepSeek test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_dashscope_tool_calling():
    """Test the tool calling behavior of Bailian model"""
    print("\n🌟 Test the Bailian model tool calling behavior")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        from langchain_core.tools import BaseTool
        
        # Create a Bailian instance
        dashscope_llm = ChatDashScope(
            model="qwen-plus",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create the same simulation tool
        class MockChinaStockDataTool(BaseTool):
            name: str = "get_china_stock_data"
            description: str = "Get market data and technical indicators for China A-share stock 000002"
            
            def _run(self, query: str = "") -> str:
                return """# 000002 Vanke A stock data analysis

## 📊 Real-time quotes
- Stock name: Vanke A
- current price: ¥6.56
- Increase or decrease: 0.61%
- Volume: 934,783 hand

## 📈 Technical indicators
- 10 day EMA: ¥6.45
- 50 day SMA: ¥6.78
- 200 day SMA: ¥7.12
- RSI: 42.5
- MACD: -0.08
- MACD signal line: -0.12
- Bollinger Bands track: ¥7.20
- Bollinger Bands Middle Track: ¥6.80
- Bollinger Bands Lower Track: ¥6.40
- ATR: 0.25"""
        
        tools = [MockChinaStockDataTool()]
        
        # Use the same prompt word
        prompt = """Please provide a detailed technical analysis of China A-share stock 000002.

Execution steps:
1. Get stock market data using get_china_stock_data tool
2. Conduct in-depth technical indicator analysis based on acquired real data
3. Output the complete technical analysis report content

Important requirements:
- Tools must be called to obtain data
- The complete content of the technical analysis report must be output, do not just describe that the report is completed
- Reports must be analyzed based on real data obtained by the tool"""
        
        # Bind the tool and call
        chain = dashscope_llm.bind_tools(tools)
        result = chain.invoke(prompt)
        
        print(f"📊 Bailian response type: {type(result)}")
        print(f"📊 Number of Bailian tool calls: {len(result.tool_calls) if hasattr(result, 'tool_calls') else 0}")
        print(f"📊 Bailian response content length: {len(result.content)}")
        print(f"📊 The first 500 characters of Bailian response content:")
        print("-" * 50)
        print(result.content[:500])
        print("-" * 50)
        
        if hasattr(result, 'tool_calls') and result.tool_calls:
            print(f"📊 Bailian tool call details:")
            for i, call in enumerate(result.tool_calls):
                print(f"   Tools{i+1}: {call.get('name', 'unknown')}")
                print(f"   parameters: {call.get('args', {})}")
        
        return result
        
    except Exception as e:
        print(f"❌ Hundred refining test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def compare_results(deepseek_result, dashscope_result):
    """Compare the results of the two models"""
    print("\n🔍 Comparative analysis of results")
    print("=" * 60)
    
    if deepseek_result and dashscope_result:
        # Tool call comparison
        deepseek_tools = len(deepseek_result.tool_calls) if hasattr(deepseek_result, 'tool_calls') else 0
        dashscope_tools = len(dashscope_result.tool_calls) if hasattr(dashscope_result, 'tool_calls') else 0
        
        print(f"📊 Tool call comparison:")
        print(f"   DeepSeek: {deepseek_tools} tool calls")
        print(f"   Bailian: {dashscope_tools} tool calls")
        
        # Content length comparison
        deepseek_length = len(deepseek_result.content)
        dashscope_length = len(dashscope_result.content)
        
        print(f"\n📝 Response content comparison:")
        print(f"   DeepSeek: {deepseek_length} character")
        print(f"   Bailian: {dashscope_length} character")
        
        # Content type analysis
        print(f"\n🔍 Content type analysis:")
        
        # Check if actual data analysis is included
        deepseek_has_data = any(keyword in deepseek_result.content for keyword in ["¥6.56", "RSI", "MACD", "Vanke A"])
        dashscope_has_data = any(keyword in dashscope_result.content for keyword in ["¥6.56", "RSI", "MACD", "Vanke A"])
        
        print(f"   DeepSeek Contains actual data: {'✅' if deepseek_has_data else '❌'}")
        print(f"   Bailian contains actual data: {'✅' if dashscope_has_data else '❌'}")
        
        # Check if it is just describing the process
        deepseek_describes_process = any(keyword in deepseek_result.content for keyword in ["first", "then", "Next", "steps"])
        dashscope_describes_process = any(keyword in dashscope_result.content for keyword in ["first", "then", "Next", "steps"])
        
        print(f"   DeepSeek Describe the analysis process: {'⚠️' if deepseek_describes_process else '✅'}")
        print(f"   Bailian describes the analysis process: {'⚠️' if dashscope_describes_process else '✅'}")
        
        # Summary
        print(f"\n📋 Summary:")
        if deepseek_tools > 0 and deepseek_has_data:
            print(f"   ✅ DeepSeek: Call the tools correctly and analyze the data")
        else:
            print(f"   ❌ DeepSeek: Tool calls or data analysis are not performed correctly")
            
        if dashscope_tools > 0 and dashscope_has_data:
            print(f"   ✅ Bailian: Call the tools correctly and analyze the data")
        else:
            print(f"   ❌ Bailian: Tool calls or data analysis are not performed correctly")

def main():
    """main function"""
    print("🔬 LLM Tool calling behavior comparison test")
    print("=" * 80)
    
    # Check API key
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    dashscope_key = os.getenv("DASHSCOPE_API_KEY")
    
    if not deepseek_key:
        print("⚠️ DEEPSEEK_API_KEY not found, skipping DeepSeek test")
        deepseek_result = None
    else:
        deepseek_result = test_deepseek_tool_calling()
    
    if not dashscope_key:
        print("⚠️ DASHSCOPE_API_KEY not found, skipping Bailian test")
        dashscope_result = None
    else:
        dashscope_result = test_dashscope_tool_calling()
    
    # Compare results
    if deepseek_result or dashscope_result:
        compare_results(deepseek_result, dashscope_result)
    else:
        print("❌ Comparison is not possible, both models failed the test")
    
    print("\n" + "=" * 80)
    print("🎯 Test completed!")

if __name__ == "__main__":
    main()
