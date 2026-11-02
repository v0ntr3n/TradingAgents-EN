#!/usr/bin/env python3
"""
Detailed debugging script to test the LLM tool calling mechanism
Simulate the actual LLM tool calling process
"""

import logging
import sys
import os
from datetime import datetime
from typing import Dict, Any

# Add project root directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from tradingagents.dataflows.realtime_news_utils import get_realtime_stock_news
from tradingagents.agents.utils.agent_utils import Toolkit

# Setup log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(name)s | %(levelname)s | %(message)s')
logger = logging.getLogger(__name__)

def test_function_exists():
    """Test whether the function exists"""
    logger.info("========== test 1: function existence check ==========")
    
    # Check directly imported functions
    logger.info(f"get_realtime_stock_news function: {get_realtime_stock_news}")
    logger.info(f"function type: {type(get_realtime_stock_news)}")
    
    # Check functions in Toolkit
    try:
        toolkit_func = getattr(Toolkit, 'get_realtime_stock_news', None)
        logger.info(f"Toolkit.get_realtime_stock_news: {toolkit_func}")
        logger.info(f"Toolkit function type: {type(toolkit_func)}")
    except Exception as e:
        logger.error(f"Failed to obtain Toolkit function: {e}")

def test_direct_call():
    """Test direct function calls"""
    logger.info("========== test 2: direct function call ==========")
    try:
        curr_date = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Call parameters: ticker='000858', date='{curr_date}'")
        
        start_time = datetime.now()
        result = get_realtime_stock_news('000858', curr_date)
        end_time = datetime.now()
        
        logger.info(f"The call was successful and took time: {(end_time - start_time).total_seconds():.2f}seconds")
        logger.info(f"Return result type: {type(result)}")
        logger.info(f"Return result length: {len(result)} character")
        logger.info(f"The first 100 characters of the result: {result[:100]}...")
        return True, result
    except Exception as e:
        logger.error(f"Direct call failed: {e}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        return False, None

def test_toolkit_call():
    """Test Toolkit calls"""
    logger.info("========== test 3: Toolkit call ==========")
    try:
        curr_date = datetime.now().strftime('%Y-%m-%d')
        logger.info(f"Call parameters: ticker='000858', date='{curr_date}'")
        
        start_time = datetime.now()
        result = Toolkit.get_realtime_stock_news('000858', curr_date)
        end_time = datetime.now()
        
        logger.info(f"Toolkit The call was successful and took time: {(end_time - start_time).total_seconds():.2f}seconds")
        logger.info(f"Return result type: {type(result)}")
        logger.info(f"Return result length: {len(result)} character")
        logger.info(f"The first 100 characters of the result: {result[:100]}...")
        return True, result
    except Exception as e:
        logger.error(f"Toolkit call failed: {e}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        return False, None

def test_toolkit_attributes():
    """Test Toolkit properties and methods"""
    logger.info("========== test 4: Toolkit Property check ==========")
    
    # List all properties of Toolkit
    toolkit_attrs = [attr for attr in dir(Toolkit) if not attr.startswith('_')]
    logger.info(f"Toolkit Available properties: {toolkit_attrs}")
    
    # Check if there is get_realtime_stock_news
    if 'get_realtime_stock_news' in toolkit_attrs:
        logger.info("✓ get_realtime_stock_news Exists in Toolkit")
    else:
        logger.warning("✗ get_realtime_stock_news Not in Toolkit")
    
    # Check toolkit type
    logger.info(f"Toolkit Type: {type(Toolkit)}")
    logger.info(f"Toolkit module: {Toolkit.__module__ if hasattr(Toolkit, '__module__') else 'N/A'}")

def simulate_llm_tool_call():
    """Simulate the LLM tool calling process"""
    logger.info("========== test 5: Simulate LLM tool calls ==========")
    
    # Parameter format for simulating LLM tool calls
    tool_call_params = {
        "name": "get_realtime_stock_news",
        "arguments": {
            "ticker": "000858",
            "date": datetime.now().strftime('%Y-%m-%d')
        }
    }
    
    logger.info(f"Simulation tool call parameters: {tool_call_params}")
    
    try:
        # Try calling via reflection
        func_name = tool_call_params["name"]
        args = tool_call_params["arguments"]
        
        if hasattr(Toolkit, func_name):
            func = getattr(Toolkit, func_name)
            logger.info(f"find function: {func}")
            
            start_time = datetime.now()
            result = func(**args)
            end_time = datetime.now()
            
            logger.info(f"The simulated LLM call is successful and time-consuming.: {(end_time - start_time).total_seconds():.2f}seconds")
            logger.info(f"Return result length: {len(result)} character")
            return True, result
        else:
            logger.error(f"function {func_name} Does not exist in Toolkit")
            return False, None
            
    except Exception as e:
        logger.error(f"Simulated LLM call failed: {e}")
        import traceback
        logger.error(f"Error details: {traceback.format_exc()}")
        return False, None

def main():
    """Main test function"""
    logger.info("Start detailed testing of LLM tool calling mechanism")
    logger.info("=" * 60)
    
    # test 1: function existence
    test_function_exists()
    
    # test 2: call directly
    direct_success, direct_result = test_direct_call()
    
    # test 3: Toolkit call
    toolkit_success, toolkit_result = test_toolkit_call()
    
    # test 4: Toolkit Property check
    test_toolkit_attributes()
    
    # test 5: Simulating LLM calls
    llm_success, llm_result = simulate_llm_tool_call()
    
    # Summary of results
    logger.info("=" * 60)
    logger.info("========== Summary of test results ==========")
    logger.info(f"direct function call: {'✓ success' if direct_success else '✗ failed'}")
    logger.info(f"Toolkit call: {'✓ success' if toolkit_success else '✗ failed'}")
    logger.info(f"Simulating LLM calls: {'✓ success' if llm_success else '✗ failed'}")
    
    # Analyze the problem
    if direct_success and not toolkit_success:
        logger.warning("🔍 Problem analysis: Toolkit There is a problem with tool binding")
    elif direct_success and not llm_success:
        logger.warning("🔍 Problem analysis: LLM There is a problem with the tool calling mechanism")
    elif not direct_success:
        logger.warning("🔍 Problem analysis: There is a problem with the function itself")
    else:
        logger.info("🔍 Problem analysis: All calls are successful")
    
    # Compare results
    if direct_success and toolkit_success:
        if direct_result == toolkit_result:
            logger.info("✓ The results of direct call and Toolkit call are the same.")
        else:
            logger.warning("⚠ The results of direct call and Toolkit call are inconsistent")
            logger.info(f"Call the result length directly: {len(direct_result)}")
            logger.info(f"Toolkit Call result length: {len(toolkit_result)}")

if __name__ == "__main__":
    main()