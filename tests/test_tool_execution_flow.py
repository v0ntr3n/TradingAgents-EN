#!/usr/bin/env python3
"""
Test tool call execution process
Verify how the ToolNode handles tool calls and returns results
"""

import sys
sys.path.append('.')

from langgraph.prebuilt import ToolNode
from langchain_core.messages import AIMessage, ToolMessage
from tradingagents.agents.utils.agent_utils import Toolkit
import json

def test_tool_execution_flow():
    """Test tool execution process"""
    print("📊 Test tool call execution process")
    print("=" * 50)
    
    try:
        # Create toolkit
        print("1. Create toolkit...")
        toolkit = Toolkit()
        print("   ✅ Toolkit created successfully")
        
        # Create ToolNode
        print("2. Create ToolNode...")
        tool_node = ToolNode([toolkit.get_stock_fundamentals_unified])
        print("   ✅ ToolNode Created successfully")
        
        # Simulate one with tool_calls AIMessage
        print("3. Create simulation AIMessage...")
        ai_message = AIMessage(
            content='I need to call a tool to get fundamental data',
            tool_calls=[{
                'name': 'get_stock_fundamentals_unified',
                'args': {'ticker': '000858', 'start_date': '2024-01-01', 'end_date': '2024-12-31'},
                'id': 'call_123'
            }]
        )
        
        print(f"   - AIMessage content: {ai_message.content}")
        print(f"   - Tool call: {ai_message.tool_calls}")
        
        # simulation state
        state = {'messages': [ai_message]}
        
        print("\n4. execute ToolNode...")
        result = tool_node.invoke(state)
        
        print(f"   - ToolNode Return type: {type(result)}")
        print(f"   - Return structure: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        if 'messages' in result:
            print(f"   - Return the number of messages: {len(result['messages'])}")
            
            for i, msg in enumerate(result['messages']):
                print(f"\n   news{i+1}:")
                print(f"     - Type: {type(msg).__name__}")
                
                if hasattr(msg, 'tool_call_id'):
                    print(f"     - tool_call_id: {msg.tool_call_id}")
                    
                if hasattr(msg, 'content'):
                    content = str(msg.content)
                    content_preview = content[:200] + '...' if len(content) > 200 else content
                    print(f"     - content length: {len(content)} character")
                    print(f"     - content Preview: {content_preview}")
                    
                    # Check if actual data is included
                    has_data = any(keyword in content for keyword in ['stocks', 'Finance', 'Revenue', 'profit', 'assets'])
                    print(f"     - Contains financial data: {'✅' if has_data else '❌'}")
        
        print("\n5. Analysis tool execution results...")
        
        # Check whether it is executed normally
        if 'messages' in result and len(result['messages']) > 0:
            tool_message = result['messages'][0]
            if isinstance(tool_message, ToolMessage):
                print("   ✅ The tool executed normally and returned ToolMessage")
                print(f"   ✅ ToolMessage of tool_call_id: {tool_message.tool_call_id}")
                print("   ✅ This ToolMessage will be added to the message history")
                print("   ✅ The system will then return to the analyst node to process the data")
            else:
                print(f"   ❌ What is returned is not ToolMessage, but: {type(tool_message)}")
        else:
            print("   ❌ No message returned")
            
    except Exception as e:
        print(f"❌ test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_tool_execution_flow()