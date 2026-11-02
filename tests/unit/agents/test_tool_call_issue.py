#!/usr/bin/env python3
"""
Detailed script for testing LLM tool calling issues
Specially analyze why LLM claims to call the tool but does not actually execute it
"""

import os
import sys
import logging
from datetime import datetime

# Add project path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.makedirs(os.path.join('data', 'logs'), exist_ok=True)

# Setup log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler(os.path.join('data', 'logs', 'test_tool_call_issue.log')),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def test_tool_call_mechanism():
    """Test tool calling mechanism"""
    logger.info("=" * 60)
    logger.info("Start testing the LLM tool calling mechanism problem")
    logger.info("=" * 60)
    
    try:
        # 1. Import necessary modules
        logger.info("1. Import module...")
        from tradingagents.llm_adapters import ChatDashScopeOpenAI
        from tradingagents.agents.utils.agent_utils import Toolkit
        from tradingagents.utils.realtime_news_utils import get_realtime_stock_news
        from langchain_core.messages import HumanMessage
        from langchain_core.tools import tool
        os.makedirs(os.path.join('data', 'logs'), exist_ok=True)
        
        # 2. Create LLM instance
        logger.info("2. Create LLM instance...")
        llm = ChatDashScopeOpenAI(
            model="qwen-plus-latest",
            temperature=0.1,
            max_tokens=1000
        )
        logger.info(f"   LLM Type: {llm.__class__.__name__}")
        
        # 3. Create Toolkit
        logger.info("3. Create Toolkit...")
        toolkit = Toolkit()
        logger.info(f"   Toolkit Created successfully")
        
        # 4. Get tools
        logger.info("4. Get tools...")
        realtime_news_tool = toolkit.get_realtime_stock_news
        logger.info(f"   Tool name: {realtime_news_tool.name}")
        logger.info(f"   Tool description: {realtime_news_tool.description}")
        
        # 5. bind tool to LLM
        logger.info("5. bind tool to LLM...")
        llm_with_tools = llm.bind_tools([realtime_news_tool])
        logger.info(f"   Tool binding completed")
        
        # 6. Test tool call
        logger.info("6. Test tool call...")
        test_message = HumanMessage(
            content="Please call the get_realtime_stock_news tool to get the latest news of 000001.SZ"
        )
        
        logger.info("   Start LLM call...")
        result = llm_with_tools.invoke([test_message])
        logger.info("   LLM Call completed")
        
        # 7. Analyze results
        logger.info("7. Analyze results...")
        logger.info(f"   result type: {type(result)}")
        logger.info(f"   Is there a tool_calls attribute?: {hasattr(result, 'tool_calls')}")
        
        if hasattr(result, 'tool_calls'):
            tool_calls = result.tool_calls
            logger.info(f"   Number of tool calls: {len(tool_calls)}")
            
            if len(tool_calls) > 0:
                logger.info("   Tool call details:")
                for i, call in enumerate(tool_calls):
                    logger.info(f"     call {i+1}:")
                    logger.info(f"       Type: {type(call)}")
                    if hasattr(call, 'name'):
                        logger.info(f"       Name: {call.name}")
                    if hasattr(call, 'args'):
                        logger.info(f"       parameters: {call.args}")
                    if isinstance(call, dict):
                        logger.info(f"       Dictionary content: {call}")
                        
                # 8. Try executing the tool call manually
                logger.info("8. Try executing the tool call manually...")
                for i, call in enumerate(tool_calls):
                    try:
                        logger.info(f"   Execute tool call {i+1}...")
                        
                        # Get parameters
                        if hasattr(call, 'args'):
                            args = call.args
                        elif isinstance(call, dict) and 'args' in call:
                            args = call['args']
                        else:
                            logger.error(f"     Unable to get parameters: {call}")
                            continue
                            
                        logger.info(f"     parameters: {args}")
                        
                        # Execution tool
                        if 'ticker' in args:
                            ticker = args['ticker']
                            logger.info(f"     call get_realtime_stock_news(ticker='{ticker}')")
                            
                            # call function directly
                            news_result = get_realtime_stock_news(ticker)
                            logger.info(f"     The function call is successful and the result length is: {len(news_result)} character")
                            logger.info(f"     The first 100 characters of the result: {news_result[:100]}...")
                            
                        else:
                            logger.error(f"     Missing in parameter ticker: {args}")
                            
                    except Exception as e:
                        logger.error(f"     Tool execution failed: {e}")
                        import traceback
                        logger.error(f"     Error details: {traceback.format_exc()}")
            else:
                logger.warning("   LLM No tools are called")
        else:
            logger.warning("   Result no tool_calls attribute")
            
        # 9. Check response content
        logger.info("9. Check response content...")
        if hasattr(result, 'content'):
            content = result.content
            logger.info(f"   Response content length: {len(content)} character")
            logger.info(f"   The first 200 characters of the response content: {content[:200]}...")
        else:
            logger.warning("   The result is no content attribute")
            
        logger.info("=" * 60)
        logger.info("Test completed")
        logger.info("=" * 60)
        
        return True
        
    except Exception as e:
        logger.error(f"test failed: {e}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        return False

if __name__ == "__main__":
    test_tool_call_mechanism()