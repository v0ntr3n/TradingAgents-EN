#!/usr/bin/env python3
"""
Test the complete tool invocation workflow
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add project root directory to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

def test_deepseek_complete_workflow():
    """Testing DeepSeek s complete tool invocation workflow"""
    print("🤖 Test the complete DeepSeek workflow")
    print("=" * 60)
    
    try:
        from tradingagents.llm_adapters.deepseek_adapter import ChatDeepSeek
        from langchain_core.tools import BaseTool
        from langchain_core.messages import HumanMessage, ToolMessage
        
        # Create DeepSeek instance
        deepseek_llm = ChatDeepSeek(
            model="deepseek-chat",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create simulation tools
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
        
        # Step 1: Send the initial request
        prompt = """Please provide a detailed technical analysis of China A-share stock 000002.

Requirements:
1. First call the get_china_stock_data tool to get the data
2. Then perform analysis based on the obtained data
3. Output a complete technical analysis report"""
        
        print("📤 Send initial request...")
        chain = deepseek_llm.bind_tools(tools)
        result1 = chain.invoke([HumanMessage(content=prompt)])
        
        print(f"📊 first response:")
        print(f"   Number of tool calls: {len(result1.tool_calls) if hasattr(result1, 'tool_calls') else 0}")
        print(f"   Response content length: {len(result1.content)}")
        print(f"   Response content: {result1.content[:200]}...")
        
        if hasattr(result1, 'tool_calls') and result1.tool_calls:
            print(f"\n🔧 Execute tool call...")
            
            # Simulation tool execution
            tool_messages = []
            for tool_call in result1.tool_calls:
                tool_name = tool_call.get('name')
                tool_id = tool_call.get('id')
                
                print(f"   Execution tool: {tool_name}")
                
                # Execution tool
                tool = tools[0]  # We only have one tool
                tool_result = tool._run("")
                
                # Create tool message
                tool_message = ToolMessage(
                    content=tool_result,
                    tool_call_id=tool_id
                )
                tool_messages.append(tool_message)
            
            # Step 2: Send tool results and request analysis generation
            print(f"\n📤 Send tool results and ask for analysis to be generated...")
            messages = [
                HumanMessage(content=prompt),
                result1,
                *tool_messages,
                HumanMessage(content="Now please generate a detailed technical analysis report based on the data obtained by the above tools. The report should contain specific data analysis and investment recommendations.")
            ]
            
            result2 = deepseek_llm.invoke(messages)
            
            print(f"📊 second response:")
            print(f"   Response content length: {len(result2.content)}")
            print(f"   The first 500 characters of the response content:")
            print("-" * 50)
            print(result2.content[:500])
            print("-" * 50)
            
            # Check if actual data analysis is included
            has_data = any(keyword in result2.content for keyword in ["¥6.56", "RSI", "MACD", "Vanke A", "42.5"])
            print(f"   Contains actual data: {'✅' if has_data else '❌'}")
            
            return result2
        else:
            print("❌ No tool calls")
            return result1
        
    except Exception as e:
        print(f"❌ DeepSeek test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_dashscope_react_agent():
    """Testing Bailian s ReAct Agent mode"""
    print("\n🌟 Test Bailian ReAct Agent mode")
    print("=" * 60)
    
    try:
        from langchain.agents import create_react_agent, AgentExecutor
        from langchain_core.prompts import PromptTemplate
        from langchain_core.tools import BaseTool
        
        # Check if you have Bailian API key
        if not os.getenv("DASHSCOPE_API_KEY"):
            print("⚠️ DASHSCOPE_API_KEY not found, skipping Bailian test")
            return None
        
        from tradingagents.llm_adapters.dashscope_adapter import ChatDashScope
        
        # Create a Bailian instance
        dashscope_llm = ChatDashScope(
            model="qwen-plus",
            temperature=0.1,
            max_tokens=2000
        )
        
        # Create tools
        class MockChinaStockDataTool(BaseTool):
            name: str = "get_china_stock_data"
            description: str = "Get market data and technical indicators for China A-share stock 000002. Called directly without parameters."
            
            def _run(self, query: str = "") -> str:
                print("🔧 [tool execution] get_china_stock_data called")
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
        
        # Create ReAct Agent
        prompt_template = """Please provide a detailed technical analysis of China A-share stock 000002.

Execution steps:
1. Get stock market data using get_china_stock_data tool
2. Conduct in-depth technical indicator analysis based on acquired real data
3. Output the complete technical analysis report content

Important requirements:
- Tools must be called to obtain data
- The complete content of the technical analysis report must be output, do not just describe that the report is completed
- Reports must be analyzed based on real data obtained by the tool

You have the following tools at your disposal:
{tools}

Use the following format:

Question: input question
Thought: You should think about what to do
Action: The action to be taken should be[{tool_names}]one of
Action Input: action input
Observation: result of action
... (This Thought/Action/Action Input/Observation can be repeated N times)
Thought: I now know the final answer
Final Answer: Final answer to original input question

Question: {input}
{agent_scratchpad}"""

        prompt = PromptTemplate.from_template(prompt_template)
        
        # Create agent
        agent = create_react_agent(dashscope_llm, tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, max_iterations=3)
        
        print("📤 execute ReAct Agent...")
        result = agent_executor.invoke({
            "input": "Please provide a detailed technical analysis of China A-share stock 000002"
        })
        
        print(f"📊 ReAct Agent result:")
        print(f"   Output length: {len(result['output'])}")
        print(f"   Output the first 500 characters of the content:")
        print("-" * 50)
        print(result['output'][:500])
        print("-" * 50)
        
        # Check if actual data analysis is included
        has_data = any(keyword in result['output'] for keyword in ["¥6.56", "RSI", "MACD", "Vanke A", "42.5"])
        print(f"   Contains actual data: {'✅' if has_data else '❌'}")
        
        return result
        
    except Exception as e:
        print(f"❌ Bailian ReAct Agent test failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    """main function"""
    print("🔬 Complete tool invocation workflow testing")
    print("=" * 80)
    
    # test DeepSeek
    deepseek_result = test_deepseek_complete_workflow()
    
    # Test one hundred refinements ReAct Agent
    dashscope_result = test_dashscope_react_agent()
    
    # Summary
    print("\n📋 Test summary")
    print("=" * 60)
    
    if deepseek_result:
        has_data = any(keyword in deepseek_result.content for keyword in ["¥6.56", "RSI", "MACD", "Vanke A"])
        print(f"✅ DeepSeek: {'Successfully generate data-based analysis' if has_data else 'Tool called but analysis is incomplete'}")
    else:
        print(f"❌ DeepSeek: test failed")
    
    if dashscope_result:
        has_data = any(keyword in dashscope_result['output'] for keyword in ["¥6.56", "RSI", "MACD", "Vanke A"])
        print(f"✅ Bailian ReAct: {'Successfully generate data-based analysis' if has_data else 'Executed but analysis is incomplete'}")
    else:
        print(f"❌ Bailian ReAct: test failed")
    
    print("\n🎯 Test completed!")

if __name__ == "__main__":
    main()
