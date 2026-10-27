"""
Testing Google Tools Processor Improvements
"""
import sys
import os
import logging
from datetime import datetime

# Add project root directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler
from tradingagents.agents.utils.agent_utils import Toolkit
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, AIMessage, SystemMessage

# Configuration log
os.makedirs(os.path.join('data', 'logs'), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join('data', 'logs', f"google_tool_handler_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
    ]
)
logger = logging.getLogger("test_google_tool_handler")

def test_google_tool_handler_improvements():
    """Testing Google Tools Processor Improvements"""
    logger.info("Start testing Google Tools processor improvements...")
    
    # Create a Google model
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro-latest", temperature=0.1)
    
    # Create toolset
    tools = [Toolkit.get_stock_market_data_unified]
    
    # test scenario 1: Check if it is a Google model
    logger.info("test scenario 1: Check if it is a Google model")
    try:
        is_google = GoogleToolCallHandler.is_google_model(llm)
        logger.info(f"Scenario 1 results: Is it a Google model?: {is_google}")
    except Exception as e:
        logger.error(f"Scenario 1 exception: {e}")
    
    # test scenario 2: Simulating empty tool calls AIMessage
    logger.info("test scenario 2: Simulating empty tool calls AIMessage")
    try:
        # Create one without tool calls AIMessage
        ai_message = AIMessage(content="I need to get stock data for analysis")
        
        state = {
            "messages": [HumanMessage(content="Please analyze Kweichow Moutai(600519)market conditions")],
            "trade_date": "2023-12-31",
            "company_of_interest": "Kweichow Moutai",
            "ticker": "600519"
        }
        
        result, messages = GoogleToolCallHandler.handle_google_tool_calls(
            result=ai_message,
            llm=llm,
            tools=tools,
            state=state,
            analysis_prompt_template="Please generate a detailed market analysis report based on the above data",
            analyst_name="market analyst"
        )
        logger.info(f"Scenario 2 results: {result[:100]}...")
    except Exception as e:
        logger.error(f"Scenario 2 exception: {e}")
    
    # test scenario 3: Simulate tool calls AIMessage
    logger.info("test scenario 3: Simulate tool calls AIMessage")
    try:
        # Create a tool call AIMessage
        ai_message = AIMessage(
            content="I need to get stock data",
            tool_calls=[{
                'id': 'test_tool_call_1',
                'name': 'get_stock_market_data_unified',
                'args': {
                    'ticker': '600519',
                    'start_date': '2023-01-01',
                    'end_date': '2023-12-31'
                }
            }]
        )
        
        state = {
            "messages": [HumanMessage(content="Please analyze Kweichow Moutai(600519)market conditions")],
            "trade_date": "2023-12-31",
            "company_of_interest": "Kweichow Moutai",
            "ticker": "600519"
        }
        
        result, messages = GoogleToolCallHandler.handle_google_tool_calls(
            result=ai_message,
            llm=llm,
            tools=tools,
            state=state,
            analysis_prompt_template="Please generate a detailed market analysis report based on the above data",
            analyst_name="market analyst"
        )
        logger.info(f"Scenario 3 results: {result[:100]}...")
    except Exception as e:
        logger.error(f"Scenario 3 exception: {e}")
    
    logger.info("Google Tool processor improvement testing completed")

if __name__ == "__main__":
    test_google_tool_handler_improvements()